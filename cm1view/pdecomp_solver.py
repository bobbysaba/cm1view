"""Pressure decomposition of CM1 output: buoyancy (p_b), linear dynamic (p_l) and
nonlinear dynamic (p_nl, the residual) pressure perturbations and the vertical
accelerations they drive (acc_b, acc_l, acc_nl).

Each part solves the anelastic pressure equation

    cp [ H d2(pi)/dx2 + H d2(pi)/dy2 + d/dz( H d(pi)/dz ) ] = F,   H = theta0_v rho0,

with its own forcing F, by a horizontal FFT (periodic lateral boundaries) or cosine
transform (open ones) and a tridiagonal solve in the vertical, conservative on CM1's
stretched grid.  p_nl is the residual: total p' - p_b - p_l.

By Bobby Saba (pdecomp_new_fixed_mp.py, the multi-CPU version of pdecomp_new_fixed.py:
same math, results identical to round-off).  cm1view runs it in a separate process
(cm1view/pdecomp.py); the pdecomp_script setting can point at another script with the
same functions instead.  It also works on its own:

    import pdecomp_solver as P
    d0 = netCDF4.Dataset("cm1out_000001.nc")
    dom, base = P.domain_info(d0), P.compute_base_state(d0)
    solver = P.setup_pressure_solver(dom, base, P.lbc_type("/path/to/run/"))
    out = P.pressure_decomposition("cm1out_000040.nc", dom, base, solver, write=False)

Threads: the heavy array work runs on strips of rows at the same time, and the
transforms use scipy's workers; PDECOMP_THREADS sets how many (default: every CPU this
process may use).  The netCDF reads stay serial (netCDF / HDF5 is not thread safe).
"""

# import required packages
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import netCDF4 as nc
from scipy.fft import fftn, ifftn, dctn, idctn

# ============================================================================
# CONSTANTS
# ============================================================================
Rd = 287.04          # dry gas constant (J/kg/K)
Rv = 461.5           # water vapor gas constant (J/kg/K)
epsilon = Rd / Rv    # ratio of gas constants
cp = 1005.7          # specific heat of dry air at constant pressure (J/kg/K)
g = 9.81             # gravitational acceleration (m/s^2)
pbb = 100000         # reference pressure for potential temperature (Pa)

# linear dynamic forcing is -LINEAR_FACTOR * rho0 * dV0/dz . grad(w). The full linearized advection
# term gives a factor of 2 (e.g., Rotunno and Klemp 1982; Markowski and Richardson 2010). Use 1.0 to
# match the equation as printed in the paper; the difference then ends up in the residual p_nl.
LINEAR_FACTOR = 2.0

# hydrometeor species that contribute to condensate loading (whichever are in the file are used)
HYDROMETEORS = ['qc', 'qr', 'qi', 'qs', 'qg', 'qhl']

# number of threads for the array work and the transforms
def _cpus():
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:  # (not on macOS)
        return os.cpu_count() or 1


THREADS = int(os.environ.get('PDECOMP_THREADS', _cpus()))

VERSION = 'cm1view pdecomp_solver.py (= pdecomp_new_fixed_mp.py)'

# ============================================================================
# THREADING HELPER
# ============================================================================
def parallel_rows(func, ny, threads = None):
    """
    Call func(rows) for strips of rows (slices along y) covering range(ny), on several threads.
    func must write its results into preallocated arrays.
    """
    threads = threads or THREADS
    nparts = 1 if threads <= 1 else min(ny, 4 * threads)
    edges = np.linspace(0, ny, nparts + 1).astype(int)
    strips = [slice(a, b) for a, b in zip(edges[:-1], edges[1:]) if b > a]
    if threads <= 1:
        for s in strips:
            func(s)
        return
    with ThreadPoolExecutor(max_workers = threads) as ex:
        for f in [ex.submit(func, s) for s in strips]:
            f.result()  # re-raise any error

# checks if variable exists in output file
def check_variable_exists(nc_file, var_name):
    """
    Check if a variable exists in a NetCDF file.

    Parameters
    ----------
    nc_file : nc.Dataset
        Open NetCDF dataset
    var_name : str
        Name of variable to check

    Returns
    -------
    bool
        True if variable exists, False otherwise
    """
    exists = var_name in nc_file.variables
    if not exists:
        print(f"Warning: Variable '{var_name}' not found in dataset")
    return exists

# pulls variable value from namelist
def query_variable_from_file(file_path, variable_name):
    """
    Queries a namelist file for a variable value.

    Parameters
    ----------
    file_path : str
        The path to the namelist file.
    variable_name : str
        The name of the variable to query.

    Returns
    -------
    np.ndarray
        The value of the queried variable.
    """
    value = None
    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            if line.startswith(variable_name):
                parts = line.split('=')
                if len(parts) == 2:
                    value = float(parts[1].strip().rstrip(','))
                    break
    if value is None:
        raise ValueError(f"Variable '{variable_name}' not found in the file.")
    return np.array(value)

# define isperiodic
def lbc_type(cm1_path):
    """
    Determine if domain has periodic lateral boundary conditions.

    Parameters
    ----------
    cm1_path : str
        Path to CM1 directory containing namelist.input

    Returns
    -------
    bool
        True if periodic, False otherwise
    """
    LBC = query_variable_from_file(f'{cm1_path}namelist.input', 'ebc')

    # define print statements based on value
    if LBC == 1:
        print("Domain has periodic lateral boundary conditions.")
    else:
        print("Domain has non-periodic lateral boundary conditions.")

    return LBC == 1  # 1=periodic, 2=non-periodic (assumes uniform boundaries)

# domain info
def domain_info(nc_file):
    """
    Read grid information. All coordinates in meters.

    Returns
    -------
    dict
        zh, zf : scalar-level and w-level heights (nz, nz+1)
        dz_layer : layer thickness zf[k+1] - zf[k] (nz)
        dz_center : spacing between scalar levels zh[k+1] - zh[k] (nz-1)
        xh, yh, dx, dy, nz, ny, nx
    """
    print("Reading domain information...")

    # mass z: newer CM1 names this 'zh', older versions 'z'
    zname = 'zh' if 'zh' in nc_file.variables else 'z'
    zf = np.squeeze(nc_file['zf'][:]).astype(float) * 1000.0  # staggered z
    zh = np.squeeze(nc_file[zname][:]).astype(float) * 1000.0
    xf = np.squeeze(nc_file['xf'][:]).astype(float) * 1000.0
    xh = np.squeeze(nc_file['xh'][:]).astype(float) * 1000.0
    yf = np.squeeze(nc_file['yf'][:]).astype(float) * 1000.0
    yh = np.squeeze(nc_file['yh'][:]).astype(float) * 1000.0

    # the spectral solver assumes uniform horizontal grid spacing
    dxx = np.diff(xf)
    dyy = np.diff(yf)
    if np.ptp(dxx) > 0.01 * dxx.mean() or np.ptp(dyy) > 0.01 * dyy.mean():
        raise ValueError("Horizontal grid spacing is not uniform; the spectral solver requires it.")

    return {'zh': zh, 'zf': zf, 'dz_layer': np.diff(zf), 'dz_center': np.diff(zh),
            'xh': xh, 'yh': yh, 'dx': dxx.mean(), 'dy': dyy.mean(),
            'nz': zh.size, 'ny': yh.size, 'nx': xh.size}

# base state handling
def compute_base_state(nc_file):
    """
    Compute reference/base state variables from the t = 0 file. All 3D arrays are (z, y, x).

    Returns
    -------
    dict
        pi0, p0 : base-state Exner function and pressure profiles (from the domain corner)
        pi0_large : full t = 0 Exner function (z, y, x)
        theta0, qv0 : horizontally averaged t = 0 potential temperature and water vapor
        theta0_v, Tv0, rho0 : base-state virtual potential temperature, virtual temperature, density
        H : theta0_v * rho0, the weight in the anelastic pressure equation
        u0, v0 : base-state wind profiles
    """
    print("Pulling and calculating base state information...")

    # Get pressure/Exner function
    if check_variable_exists(nc_file, "pi"):
        pi0_large = np.squeeze(nc_file['pi'][0]).astype(float)
    elif check_variable_exists(nc_file, "prs"):
        pi0_large = (np.squeeze(nc_file['prs'][0]).astype(float) / pbb) ** (Rd / cp)
    else:
        raise ValueError("No pressure variable found in dataset. Need pi, or prs")
    pi0 = pi0_large[:, 0, 0]
    p0 = pbb * pi0 ** (cp / Rd)

    # Get wind components
    if check_variable_exists(nc_file, "u"):
        u0 = np.squeeze(nc_file['u'][0,:,0,0]).astype(float)
    else:
        u0 = np.squeeze(nc_file['uinterp'][0,:,0,0]).astype(float)

    if check_variable_exists(nc_file, "v"):
        v0 = np.squeeze(nc_file['v'][0,:,0,0]).astype(float)
    else:
        v0 = np.squeeze(nc_file['vinterp'][0,:,0,0]).astype(float)

    # Get thermodynamic variables
    theta0 = np.squeeze(np.mean(nc_file['th'][0], axis = (1,2))).astype(float)
    qv0 = np.squeeze(np.mean(nc_file['qv'][0], axis = (1,2))).astype(float)

    # Virtual potential temperature
    theta0_v = theta0 * (1 + (Rv / Rd - 1) * qv0) / (1 + qv0)

    # virtual temperature
    Tv0 = theta0_v * pi0

    # density
    rho0 = p0 / (Rd * Tv0)

    return {'pi0': pi0, 'p0': p0, 'pi0_large': pi0_large, 'theta0': theta0, 'qv0': qv0,
            'theta0_v': theta0_v, 'Tv0': Tv0, 'rho0': rho0, 'H': theta0_v * rho0,
            'u0': u0, 'v0': v0}

# pressure solver/coefficient matrices
def setup_pressure_solver(domain, base_state, isperiodic):
    """
    Set up the solver for

        cp * [ H d2(pi)/dx2 + H d2(pi)/dy2 + d/dz( H d(pi)/dz ) ] = F,   H = theta0_v * rho0,

    with d(pi)/dz = 0 at the lower and upper boundaries. In the vertical, level k is

        L pi_k + ( H_{k+1/2} (pi_{k+1} - pi_k) / dzc_{k+1/2} - H_{k-1/2} (pi_k - pi_{k-1}) / dzc_{k-1/2} ) / (H_k dz_k)
            = F_k / (cp H_k)

    where L is the horizontal Laplacian eigenvalue, dz_k is the layer thickness and dzc is the spacing
    between scalar levels. Multiplying by H_k dz_k and summing over k telescopes the vertical part, so
    the solver is conservative on the stretched grid.
    """
    H = base_state['H']
    dz = domain['dz_layer']
    dzc = domain['dz_center']
    Hf = 0.5 * (H[:-1] + H[1:])  # H at interior w-levels

    nz = domain['nz']
    cfa = np.zeros(nz)  # lower diagonal
    cfc = np.zeros(nz)  # upper diagonal
    cfa[1:] = Hf / (H[1:] * dz[1:] * dzc)
    cfc[:-1] = Hf / (H[:-1] * dz[:-1] * dzc)

    # horizontal Laplacian eigenvalues (second-order finite differences)
    ky = np.arange(domain['ny'])
    kx = np.arange(domain['nx'])
    if isperiodic:
        Ly = 2 * (np.cos(2 * np.pi * ky / domain['ny']) - 1) / domain['dy']**2
        Lx = 2 * (np.cos(2 * np.pi * kx / domain['nx']) - 1) / domain['dx']**2
    else:
        # cosine transform = method of images (zero-gradient lateral boundaries)
        Ly = 2 * (np.cos(np.pi * ky / domain['ny']) - 1) / domain['dy']**2
        Lx = 2 * (np.cos(np.pi * kx / domain['nx']) - 1) / domain['dx']**2
    L = Ly[:, np.newaxis] + Lx[np.newaxis, :]

    return {'cfa': cfa, 'cfc': cfc, 'L': L, 'H': H, 'Hf': Hf, 'dz': dz, 'dzc': dzc,
            'isperiodic': isperiodic}

def solve_pressure_equation(F, solver):
    """
    Solve the pressure equation for forcing F (z, y, x). Returns the Exner perturbation (z, y, x)
    with its volume mean removed.
    """
    cfa, cfc, L, H = solver['cfa'], solver['cfc'], solver['L'], solver['H']
    nz, ny = F.shape[0], F.shape[1]

    rhs = np.empty(F.shape)
    def scale(rows):
        rhs[:, rows] = F[:, rows] / (cp * H[:, np.newaxis, np.newaxis])
    parallel_rows(scale, ny)

    # transform in the horizontal
    if solver['isperiodic']:
        rhs_hat = fftn(rhs, axes = (1,2), workers = THREADS)
    else:
        rhs_hat = dctn(rhs, type = 2, axes = (1,2), norm = 'ortho', workers = THREADS)
    del rhs

    # the (0,0) horizontal mode is singular (pi is only defined up to a constant); integrate it directly
    rhs_00 = rhs_hat[:, 0, 0].copy()

    # Thomas algorithm for all other modes: cfa*pi_{k-1} + (L - cfa - cfc)*pi_k + cfc*pi_{k+1} = rhs
    # (each horizontal mode is an independent tridiagonal system: strips of rows run in parallel)
    L_safe = L.copy()
    L_safe[0, 0] = -1.0  # placeholder, overwritten below
    pi_hat = np.empty(rhs_hat.shape, dtype = rhs_hat.dtype)

    def sweep(rows):
        Ls = L_safe[rows]
        r = rhs_hat[:, rows]
        cprime = np.zeros(r.shape, dtype = r.dtype)
        dprime = np.zeros(r.shape, dtype = r.dtype)

        denom = Ls - cfa[0] - cfc[0]
        cprime[0] = cfc[0] / denom
        dprime[0] = r[0] / denom
        for iz in range(1, nz):
            denom = (Ls - cfa[iz] - cfc[iz]) - cfa[iz] * cprime[iz-1]
            cprime[iz] = cfc[iz] / denom
            dprime[iz] = (r[iz] - cfa[iz] * dprime[iz-1]) / denom

        for iz in range(nz - 2, -1, -1):  # back substitution in place
            dprime[iz] = dprime[iz] - cprime[iz] * dprime[iz+1]
        pi_hat[:, rows] = dprime

    parallel_rows(sweep, ny)
    del rhs_hat

    # (0,0) mode: H_k dz_k rhs_k sums to the flux through the top of layer k. Remove any net column
    # source first (it must be zero for a solution to exist with zero-gradient top and bottom).
    w_col = H * solver['dz']
    rhs_00 = rhs_00 - np.sum(w_col * rhs_00) / np.sum(w_col)
    flux = np.cumsum(w_col * rhs_00)[:-1]  # at interior w-levels
    pi_00 = np.zeros(nz, dtype = pi_hat.dtype)
    pi_00[1:] = np.cumsum(flux * solver['dzc'] / solver['Hf'])
    pi_hat[:, 0, 0] = pi_00

    # inverse transform
    if solver['isperiodic']:
        pi = ifftn(pi_hat, axes = (1,2), workers = THREADS).real
    else:
        pi = idctn(pi_hat, type = 2, axes = (1,2), norm = 'ortho', workers = THREADS)

    return pi - np.mean(pi)  # Remove mean (non-uniqueness)

def interp_to_w_levels(var, domain):
    """
    Linearly interpolate a scalar-level field (z, ...) to the interior w-levels. Returns an array
    with nz+1 levels whose top and bottom levels are zero.
    """
    zh, zf = domain['zh'], domain['zf']
    wgt = (zf[1:-1] - zh[:-1]) / (zh[1:] - zh[:-1])
    wgt = wgt.reshape((-1,) + (1,) * (var.ndim - 1))
    out = np.zeros((var.shape[0] + 1,) + var.shape[1:])
    if var.ndim == 3:
        def rows_(rows):
            v = var[:, rows]
            out[1:-1, rows] = v[:-1] + wgt * (v[1:] - v[:-1])
        parallel_rows(rows_, var.shape[1])
    else:
        out[1:-1] = var[:-1] + wgt * (var[1:] - var[:-1])
    return out

def compute_buoyancy(nc_file, base_state):
    """
    Buoyancy B = g * (theta'/theta0 + (Rv/Rd - 1) qv' - q_hydrometeors) on scalar levels (z, y, x).
    """
    theta = np.squeeze(nc_file['th'][0]).astype(float)
    qv = np.squeeze(nc_file['qv'][0]).astype(float)

    q_hydro = np.zeros_like(theta)
    used = []
    for q in HYDROMETEORS:
        if q in nc_file.variables:
            q_hydro += np.squeeze(nc_file[q][0])
            used.append(q)
    print(f"  Condensate loading from: {', '.join(used)}")

    theta0 = base_state['theta0'][:, np.newaxis, np.newaxis]
    qv0 = base_state['qv0'][:, np.newaxis, np.newaxis]

    B = np.empty_like(theta)
    def rows_(rows):
        B[:, rows] = g * ((theta[:, rows] - theta0) / theta0 + (Rv / Rd - 1) * (qv[:, rows] - qv0)
                          - q_hydro[:, rows])
    parallel_rows(rows_, theta.shape[1])
    return B

# compute_buoyancy_pressure
def compute_buoyancy_pressure(B, domain, base_state, solver):
    """
    Buoyancy pressure: forcing d(rho0 B)/dz in flux form on the stretched grid, with rho0 B = 0 at the
    lower and upper boundaries (w = 0 there). The column integral of this forcing is exactly zero.
    """
    rho0 = base_state['rho0'][:, np.newaxis, np.newaxis]
    rhoB = np.empty_like(B)
    def mult(rows):
        rhoB[:, rows] = rho0 * B[:, rows]
    parallel_rows(mult, B.shape[1])
    rhoB_w = interp_to_w_levels(rhoB, domain)
    del rhoB

    dz = domain['dz_layer'][:, np.newaxis, np.newaxis]
    forcing = np.empty(B.shape)
    def diff(rows):
        forcing[:, rows] = (rhoB_w[1:, rows] - rhoB_w[:-1, rows]) / dz
    parallel_rows(diff, B.shape[1])
    del rhoB_w

    # sanity check: the column integral should vanish to round-off
    col = np.tensordot(domain['dz_layer'], forcing, axes = (0, 0))
    print(f"  Buoyancy forcing column-integral check (should be ~1e-16): "
          f"{np.abs(col).max() / (np.abs(forcing).max() * domain['zf'][-1]):.1e}")

    return solve_pressure_equation(forcing, solver)

# compute_linear_dynamic_pressure
def compute_linear_dynamic_pressure(nc_file, domain, base_state, solver):
    """
    Linear dynamic pressure: forcing -LINEAR_FACTOR * rho0 * (dU0/dz dw/dx + dV0/dz dw/dy).
    """
    # pull w on scalar levels (z, y, x)
    if check_variable_exists(nc_file, "w"):
        w = 0.5 * (np.squeeze(nc_file['w'][0,0:-1]) + np.squeeze(nc_file['w'][0,1:])).astype(float)
    else:
        w = np.squeeze(nc_file['winterp'][0]).astype(float)

    # horizontal derivatives: each level is independent (strips of levels on the threads)
    dwdx = np.empty_like(w)
    dwdy = np.empty_like(w)
    def grads(levels):
        dwdx[levels] = np.gradient(w[levels], domain['dx'], axis = 2)
        dwdy[levels] = np.gradient(w[levels], domain['dy'], axis = 1)
    parallel_rows(grads, w.shape[0])
    del w

    # base-state shear on the stretched grid
    dudz = np.gradient(base_state['u0'], domain['zh'])[:, np.newaxis, np.newaxis]
    dvdz = np.gradient(base_state['v0'], domain['zh'])[:, np.newaxis, np.newaxis]
    rho0 = base_state['rho0'][:, np.newaxis, np.newaxis]

    forcing = np.empty_like(dwdx)
    def force(rows):
        forcing[:, rows] = -LINEAR_FACTOR * rho0 * (dudz * dwdx[:, rows] + dvdz * dwdy[:, rows])
    parallel_rows(force, forcing.shape[1])
    del dwdx, dwdy

    return solve_pressure_equation(forcing, solver)

# post processing
def post_process(pi_b, pi_l, pi_nl, rho, B, domain, base_state):
    """
    Convert Exner perturbations to pressure perturbations (Pa) and compute vertical accelerations.
    """
    pi0_large = base_state['pi0_large']
    ny = pi0_large.shape[1]
    zh = domain['zh']

    print("Converting to pressure units...")
    out = {k: np.empty(pi0_large.shape) for k in ('p_b', 'p_l', 'p_nl', 'acc_b', 'acc_l', 'acc_nl')}
    def rows_(rows):
        p0 = pi0_large[:, rows]
        p_t0 = pbb * p0 ** (cp / Rd)
        pb_pert  = pbb * (p0 + pi_b[:, rows])  ** (cp / Rd) - p_t0
        pl_pert  = pbb * (p0 + pi_l[:, rows])  ** (cp / Rd) - p_t0
        pnl_pert = pbb * (p0 + pi_nl[:, rows]) ** (cp / Rd) - p_t0
        out['p_b'][:, rows], out['p_l'][:, rows], out['p_nl'][:, rows] = pb_pert, pl_pert, pnl_pert

        # gradients along z: each column is independent
        dpb_dz  = np.gradient(pb_pert, zh, axis = 0)
        dpl_dz  = np.gradient(pl_pert, zh, axis = 0)
        dpnl_dz = np.gradient(pnl_pert, zh, axis = 0)

        r = rho[:, rows]
        out['acc_b'][:, rows]  = B[:, rows] - (1.0 / r) * dpb_dz
        out['acc_l'][:, rows]  = -(1.0 / r) * dpl_dz
        out['acc_nl'][:, rows] = -(1.0 / r) * dpnl_dz
    print("Computing gradients...")
    print("Computing accelerations...")
    parallel_rows(rows_, ny)

    return out

def write_data(ds, post_data):
    """
    Write data to netcdf file. All fields are (z, y, x).

    Parameters
    ----------
    ds : netCDF4.Dataset
        NetCDF4 object to write data to
    post_data : dict
        Dictionary containing data to write to netCDF file
    """
    print("Writing data to netCDF file.")
    vars_info = {'p_b': ('pressure perturbation due to buoyancy', 'Pa'),
                'p_l': ('pressure perturbation due to linear term', 'Pa'),
                'p_nl': ('pressure perturbation due to non-linear term (residual)', 'Pa'),
                'acc_b': ('acceleration due to buoyancy', 'm/s^2'),
                'acc_l': ('acceleration due to linear term', 'm/s^2'),
                'acc_nl': ('acceleration due to non-linear term (residual)', 'm/s^2')}

    # scalar-grid dimension names (newer CM1 uses zh/yh/xh, older versions nk/nj/ni)
    if 'zh' in ds.dimensions:
        dims = ('time', 'zh', 'yh', 'xh')
    else:
        dims = ('time', 'nk', 'nj', 'ni')

    for var, (long_name, units) in vars_info.items():
        if var in ds.variables:
            nc_var = ds[var]
        else:
            nc_var = ds.createVariable(var, 'f8', dims)
        nc_var.long_name = long_name
        nc_var.units = units
        nc_var.pdecomp_version = VERSION
        nc_var[0,:,:,:] = post_data[var]

    ds.sync()
    print("Data written and synced to netCDF file.")

# main decomposition function
def pressure_decomposition(filepath, domain, base_state, solver, write = True):
    """
    Perform complete pressure decomposition on CM1 output file.

    Parameters
    ----------
    filepath : str
        Path to CM1 output NetCDF file
    write : bool, optional
        Write p_b, p_l, p_nl and the accelerations into the file (default: True)

    Returns
    -------
    dict
        p_b, p_l, p_nl (Pa) and acc_b, acc_l, acc_nl (m/s^2), all (z, y, x)
    """
    print(f"Opening dataset... ({THREADS} threads)")
    ds = nc.Dataset(filepath, 'r+' if write else 'r')

    # pull some variables needed for future math
    pi = np.squeeze(ds['pi'][0]).astype(float) # non-dimensional pressure
    rho = np.squeeze(ds['rho'][0]).astype(float) # density

    print("Computing buoyancy...")
    B = compute_buoyancy(ds, base_state)

    print("Computing buoyancy pressure...")
    pi_b = compute_buoyancy_pressure(B, domain, base_state, solver)

    print("Computing linear dynamic pressure...")
    pi_l = compute_linear_dynamic_pressure(ds, domain, base_state, solver)

    print("Computing nonlinear dynamic pressure...")

    # non-linear is the residual of the pressure perturbation
    pi0_large = base_state['pi0_large']
    pi_nl = np.empty_like(pi)
    def rows_(rows):
        pi_nl[:, rows] = (pi[:, rows] - pi0_large[:, rows]) - pi_l[:, rows] - pi_b[:, rows]
    parallel_rows(rows_, pi.shape[1])
    del pi

    print("Post processing...")
    post_proc = post_process(pi_b, pi_l, pi_nl, rho, B, domain, base_state)

    # write data to netcdf file
    if write:
        write_data(ds, post_proc)

    # close dataset
    ds.close()

    print("Decomposition complete!")

    return post_proc
