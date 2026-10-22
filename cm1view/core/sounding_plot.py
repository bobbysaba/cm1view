"""Matplotlib sounding graphics (skew-T, hodograph, profiles) + HTML table."""

import numpy as np
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.transforms import blended_transform_factory
from metpy.plots import SkewT

from ..theme import BG, PANEL, GRID, TEXT, MUTED, ACCENT

KT = 1.943844
HODO_BANDS = [(0, 1, "#f43f5e"), (1, 3, "#22c55e"), (3, 6, "#eab308"),
              (6, 9, "#38bdf8"), (9, 12, "#a78bfa")]


def _style(ax):
    ax.set_facecolor(PANEL)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    ax.title.set_color(TEXT)


def _wfac(units):
    return KT if units == "kt" else 1.0


def wind_dir_spd(u, v, units):
    spd = np.hypot(u, v) * _wfac(units)
    d = (270.0 - np.degrees(np.arctan2(v, u))) % 360.0
    return f"{d:03.0f}°/{spd:.0f}"


# ------------------------------------------------------------ skew-T + hodo
# Comparison styles for several soundings:
#   "lines":  colour = quantity (T red, Td green, ...), line style = sounding
#   "colors": colour = sounding, line style = quantity
LINESTYLES = ["-", (0, (5, 2.5)), (0, (1.2, 1.8)), (0, (7, 2, 1.5, 2))]
T_COLOR, TD_COLOR, PARCEL_COLOR = "#f87171", "#4ade80", "#e5e7eb"

# user-adjustable look of the sounding graphics (Plot style panel); None = automatic
STYLE = dict(t_color=T_COLOR, td_color=TD_COLOR, parcel_color=PARCEL_COLOR,
             lw=2.2, parcel_lw=1.3, hodo_lw=2.4, base_color=MUTED, shade=True, barbs=True,
             guides=True, ring=None, hodo_top=12.0, tmin=None, tmax=None, ptop=100.0,
             prof_lw=1.8)


def _st(style):
    return dict(STYLE, **(style or {}))


def _legend(ax, handles, loc, ncol=1, fontsize=7.5):
    leg = ax.legend(handles=handles, loc=loc, fontsize=fontsize, frameon=True, ncol=ncol,
                    facecolor=BG, edgecolor=GRID, labelcolor=TEXT, handlelength=2.6)
    leg.get_frame().set_alpha(0.88)
    return leg


def _sounding_handles(items, style, base):
    hs = []
    for n, (label, color, _) in enumerate(items):
        if style == "colors":
            hs.append(Line2D([], [], color=color, lw=2.2, label=label))
        else:
            hs.append(Line2D([], [], color=TEXT, lw=1.8, ls=LINESTYLES[n], label=label))
    if base is not None:
        hs.append(Line2D([], [], color=MUTED, lw=1.2, ls="--", label="Base state"))
    return hs


def skewt_hodo_figure(items, base=None, parcel="ml", units="m/s", width=9.0, style="lines",
                      look=None, limits=None):
    """items: list of (label, color, result) from thermo.analyze.  look: STYLE
    overrides.  limits: dict(skew=(T at bottom-left, T at bottom-right, p bottom, p top),
    hodo=(u0, u1, v0, v1) in `units`) for a zoomed view.  The axes are kept on the
    figure as fig.cv_axes = {'skew': ax, 'hodo': hx}."""
    lk, limits = _st(look), limits or {}
    # pressure range in view: annotations (barbs, height / LCL labels) outside it are
    # left out, since they are drawn in axes coordinates and would spill over the frame
    p_view = (limits["skew"][2], limits["skew"][3]) if limits.get("skew") else \
        (1050.0, lk["ptop"])

    def in_view(pk):
        return np.isfinite(pk) and min(p_view) <= pk <= max(p_view)

    fig = Figure(figsize=(width, width * 0.56), facecolor=BG)
    gs = GridSpec(1, 2, figure=fig, width_ratios=[1.35, 1.0], wspace=0.12,
                  left=0.075, right=0.985, top=0.93, bottom=0.08)
    # zoomed: let the limits fill the panel (MetPy's fixed aspect would shrink it)
    skew = SkewT(fig, rotation=45, subplot=gs[0, 0],
                 aspect="auto" if limits.get("skew") else 80.5)
    ax = skew.ax
    _style(ax)
    ax.set_ylim(1050, lk["ptop"])
    if lk["guides"]:
        skew.plot_dry_adiabats(colors="#c2410c", alpha=0.18, linewidth=0.7)
        skew.plot_moist_adiabats(colors="#15803d", alpha=0.18, linewidth=0.7)
        skew.plot_mixing_lines(colors="#0e7490", alpha=0.25, linewidth=0.7)
    ax.axvline(0, color="#60a5fa", lw=0.8, alpha=0.5, ls="--")
    ax.grid(True, color=GRID, lw=0.5, alpha=0.8)
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("Pressure (hPa)")
    wf = _wfac(units)

    single = len(items) == 1
    by_color = style == "colors" and not single
    tmin, tmax = 1e9, -1e9
    if base is not None:
        bp = base["prof"]
        ax.plot(bp["T"] - 273.15, bp["p"] / 100, color=lk["base_color"], lw=1.2, ls="--",
                alpha=0.9)
        ax.plot(bp["Td"] - 273.15, bp["p"] / 100, color=lk["base_color"], lw=1.2, ls=":",
                alpha=0.9)
    for n, (label, color, r) in enumerate(items):
        pr = r["prof"]
        p = pr["p"] / 100.0
        T, Td = pr["T"] - 273.15, pr["Td"] - 273.15
        if by_color:
            (cT, lsT), (cTd, lsTd) = (color, "-"), (color, "--")
        else:
            (cT, lsT), (cTd, lsTd) = ((lk["t_color"], LINESTYLES[n]),
                                      (lk["td_color"], LINESTYLES[n]))
        ax.plot(T, p, color=cT, lw=lk["lw"], ls=lsT)
        ax.plot(Td, p, color=cTd, lw=lk["lw"], ls=lsTd)
        tmin, tmax = min(tmin, np.nanmin(Td[p > 300])), max(tmax, np.nanmax(T))
        par = r[parcel]
        Tp = par["T"] - 273.15
        ok = np.isfinite(Tp)
        ax.plot(Tp[ok], p[ok], color=color if by_color else lk["parcel_color"],
                lw=lk["parcel_lw"] * (1.0 if n == 0 else 0.77), alpha=0.9 if n == 0 else 0.6,
                ls=(0, (4, 2)) if (single or by_color) else LINESTYLES[n])
        if n == 0 and lk["shade"]:
            ax.fill_betweenx(p[ok], T[ok], Tp[ok], where=Tp[ok] > T[ok],
                             color="#f87171", alpha=0.18, lw=0)
            ax.fill_betweenx(p[ok], T[ok], Tp[ok], where=(Tp[ok] < T[ok]) & (p[ok] > 500),
                             color="#60a5fa", alpha=0.12, lw=0)
        if n == 0:
            trans = blended_transform_factory(ax.transAxes, ax.transData)
            for key, name in (("lcl_z", "LCL"), ("lfc_z", "LFC"), ("el_z", "EL")):
                zk = par[key]
                pk = np.exp(np.interp(zk, pr["z"], np.log(p))) if np.isfinite(zk) else np.nan
                if in_view(pk):
                    ax.plot([0.77, 0.81], [pk, pk], color=ACCENT, lw=1.5, transform=trans)
                    ax.text(0.815, pk, name, color=ACCENT, fontsize=8, va="center",
                            transform=trans)
            for zk in (1, 3, 6, 9, 12):
                pk = np.exp(np.interp(zk * 1000.0, pr["z"], np.log(p)))
                if zk * 1000 < pr["z"][-1] and in_view(pk):
                    ax.text(0.012, pk, f"{zk} km", color=MUTED, fontsize=7.5,
                            va="center", transform=trans)
        # barbs, ~36 evenly spaced in log p over the view (so the same spacing on screen
        # at any zoom); one column per sounding, labelled on top
        step = np.log(max(p_view) / min(p_view)) / 36.0
        sel, last = [], np.inf
        for k in range(p.size):
            if p[k] < min(p_view):
                break
            if in_view(p[k]) and last - np.log(p[k]) >= step:
                sel.append(k)
                last = np.log(p[k])
        sel = np.array(sel)
        xloc = 0.96 - 0.05 * n
        bc = color if by_color else TEXT
        if lk["barbs"] and sel.size:
            skew.plot_barbs(p[sel], pr["u"][sel] * KT, pr["v"][sel] * KT, xloc=xloc, color=bc,
                            length=5.5, linewidth=0.7)
        if not single and lk["barbs"]:
            ax.text(xloc, 1.0, label.split(" ")[0], color=bc, fontsize=7, ha="center",
                    va="bottom", transform=ax.transAxes)
    ax.set_xlim(lk["tmin"] if lk["tmin"] is not None else max(-45, np.floor(tmin / 10) * 10 - 5),
                lk["tmax"] if lk["tmax"] is not None else min(55, np.ceil(tmax / 10) * 10 + 10))
    if limits.get("skew"):  # zoomed: temperatures along the bottom edge, pressure range
        t0, t1, pb, pt = limits["skew"]
        ax.set_ylim(pb, pt)
        ax.set_xlim(t0, t1)
    pname = {"sb": "SB", "ml": "ML", "mu": "MU"}[parcel]
    ax.set_title(f"Skew-T  ·  {pname} parcel", fontsize=10, loc="left", color=TEXT)
    if not single or base is not None:
        _legend(ax, _sounding_handles(items, style, base), "lower left")

    # ---------------------------------------------------------- hodograph
    hx = fig.add_subplot(gs[0, 1])
    _style(hx)
    # equal u / v scale, kept by choosing limits that match the panel's shape (so a
    # zoomed view keeps the panel size and needs no aspect adjustment)
    pos = hx.get_position()
    box_ratio = (pos.height * fig.get_figheight()) / (pos.width * fig.get_figwidth())

    def square(u0, u1, v0, v1):
        cu_, cv_ = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
        hu, hv = 0.5 * abs(u1 - u0), 0.5 * abs(v1 - v0)
        hu, hv = max(hu, hv / box_ratio), max(hv, hu * box_ratio)
        return (cu_ - hu, cu_ + hu), (cv_ - hv, cv_ + hv)
    allu, allv = [], []
    htop = lk["hodo_top"] * 1000.0
    for _, _, r in items:
        pr = r["prof"]
        s = pr["z"] <= htop
        allu += list(pr["u"][s] * wf) + [r["kin"]["rm"][0] * wf, r["kin"]["lm"][0] * wf]
        allv += list(pr["v"][s] * wf) + [r["kin"]["rm"][1] * wf, r["kin"]["lm"][1] * wf]
    allu, allv = np.array(allu), np.array(allv)
    ring = lk["ring"] or (10.0 if units == "m/s" else 20.0)
    rmax = max(np.hypot(allu, allv).max(), ring) * 1.1
    cu, cv = 0.5 * (allu.max() + allu.min()), 0.5 * (allv.max() + allv.min())
    half = max(allu.max() - allu.min(), allv.max() - allv.min()) * 0.6 + ring * 0.5
    for rr in np.arange(ring, rmax + ring, ring):
        hx.add_patch(Circle((0, 0), rr, fill=False, color=GRID, lw=0.8))
        hx.text(rr * 0.7071, -rr * 0.7071, f"{rr:.0f}", color=MUTED, fontsize=7,
                ha="center", va="center", clip_on=True)
    hx.axhline(0, color=GRID, lw=0.8)
    hx.axvline(0, color=GRID, lw=0.8)
    for n, (label, color, r) in enumerate(items):
        pr, kin = r["prof"], r["kin"]
        z, u, v = pr["z"] / 1000.0, pr["u"] * wf, pr["v"] * wf
        if by_color:
            s = z <= lk["hodo_top"]
            hx.plot(u[s], v[s], color=color, lw=lk["hodo_lw"] * 0.92)
            for zk in (1, 3, 6):
                hx.plot(np.interp(zk, z, u), np.interp(zk, z, v), "o", ms=3.5,
                        color=color, mec=BG, mew=0.6)
        else:
            for z0, z1, c in HODO_BANDS:
                if z0 >= lk["hodo_top"]:
                    continue
                z1 = min(z1, lk["hodo_top"])
                s = (z >= z0) & (z <= z1)
                if s.sum() > 1:
                    zz = np.concatenate(([z0], z[s], [z1]))
                    hx.plot(np.interp(zz, z, u), np.interp(zz, z, v), color=c,
                            lw=lk["hodo_lw"] * (1.0 if n == 0 else 0.83), ls=LINESTYLES[n])
        rm, lm, c = np.array(kin["rm"]) * wf, np.array(kin["lm"]) * wf, np.array(kin["storm"]) * wf
        mc = color if by_color else TEXT
        tag = "" if single else label.split(" ")[0]
        hx.text(*rm, f"RM{tag}", color=mc, fontsize=7.5, ha="center", va="center",
                weight="bold")
        hx.text(*lm, f"LM{tag}", color=mc, fontsize=7.5, ha="center", va="center",
                weight="bold")
        hx.plot(*c, marker="o", ms=9, mfc="none", mec=color if by_color else ACCENT, mew=1.6)
        if n == 0:
            hx.plot([c[0], u[0]], [c[1], v[0]], color=ACCENT, lw=0.9, ls=":")
            z5 = np.interp(0.5, z, u), np.interp(0.5, z, v)
            hx.plot([u[0], z5[0]], [v[0], z5[1]], color=ACCENT, lw=0.9, ls=":")
    if base is not None:
        bp = base["prof"]
        s = bp["z"] <= htop
        hx.plot(bp["u"][s] * wf, bp["v"][s] * wf, color=lk["base_color"], lw=1.2, ls="--")
    xl, yl = square(*(limits.get("hodo") or (cu - half, cu + half, cv - half, cv + half)))
    hx.set_xlim(*xl)
    hx.set_ylim(*yl)
    hx.set_xlabel(f"u ({units})")
    hx.set_ylabel(f"v ({units})")
    hx.set_title("Hodograph (ground-relative)", fontsize=10, loc="left", color=TEXT)
    if not by_color:
        handles = [Line2D([], [], color=c, lw=lk["hodo_lw"], label=f"{a}–{min(b, lk['hodo_top']):g} km")
                   for a, b, c in HODO_BANDS if a < lk["hodo_top"]]
        handles.append(Line2D([], [], marker="o", ms=7, mfc="none", mec=ACCENT, lw=0,
                              label="Storm motion"))
        _legend(hx, handles, "upper left", fontsize=7)
    fig.cv_axes = {"skew": ax, "hodo": hx}
    return fig


# ------------------------------------------------------------ profiles
PROFILE_PANELS = [  # title, x label
    ("Storm-relative wind", "speed ({units})"),
    ("Vertical wind shear", "|dV/dz| (10⁻³ s⁻¹)"),
    ("Horizontal vorticity", "ω (10⁻³ s⁻¹)"),
    ("Cumulative SRH", "SRH, 0–z (m² s⁻²)"),
    ("Potential temperature", "θ / θe (K)"),
]
QCOL = dict(main=ACCENT, ws="#f472b6", wc="#38bdf8", th=T_COLOR, the=TD_COLOR)


def profiles_figure(items, base=None, zmax=6.0, units="m/s", width=9.0, style="lines",
                    look=None, limits=None):
    """limits: dict(z=(z0, z1) km, x={panel index: (x0, x1)}) for a zoomed view.  The
    panels are kept on the figure as fig.cv_axes = {'prof0': ax, ...}."""
    lk, limits = _st(look), limits or {}
    qcol = dict(QCOL, th=lk["t_color"], the=lk["td_color"])
    fig = Figure(figsize=(width, width * 0.44), facecolor=BG)
    axs = fig.subplots(1, 5, sharey=True,
                       gridspec_kw=dict(wspace=0.12, left=0.07, right=0.99, top=0.84,
                                        bottom=0.17))
    wf = _wfac(units)
    for ax, (title, xl) in zip(axs, PROFILE_PANELS):
        _style(ax)
        ax.set_title(title, fontsize=9, loc="left", color=TEXT)
        ax.set_xlabel(xl.format(units=units), fontsize=8)
        ax.grid(True, color=GRID, lw=0.5)
    axs[0].set_ylabel("Height (km AGL)")
    axs[0].set_ylim(0, zmax)
    single = len(items) == 1
    by_color = style == "colors" and not single

    def draw(r, n, color=None, base_state=False):
        pf, pr = r["profiles"], r["prof"]
        zm, z = pf["zm"] / 1000.0, pf["z"] / 1000.0
        if base_state:
            col = dict.fromkeys(QCOL, lk["base_color"])
            ls_a, ls_b, lw = "--", ":", 1.2
        elif by_color:
            col = dict.fromkeys(QCOL, color)
            ls_a, ls_b, lw = "-", ":", lk["prof_lw"]
        else:
            col, ls_a, lw = qcol, LINESTYLES[n], lk["prof_lw"]
            ls_b = ls_a
        axs[0].plot(pf["sr_speed"] * wf, zm, color=col["main"], lw=lw, ls=ls_a)
        axs[1].plot(pf["shear"] * 1e3, zm, color=col["main"], lw=lw, ls=ls_a)
        axs[2].plot(pf["ws"] * 1e3, zm, color=col["ws"], lw=lw, ls=ls_a)
        axs[2].plot(pf["wc"] * 1e3, zm, color=col["wc"], lw=lw * 0.8, ls=ls_b)
        axs[3].plot(pf["cum_srh"], z, color=col["main"], lw=lw, ls=ls_a)
        axs[4].plot(pr["th"], z, color=col["th"], lw=lw, ls=ls_a)
        axs[4].plot(pr["the"], z, color=col["the"], lw=lw * 0.8, ls=ls_b)

    if base is not None:
        draw(base, 0, base_state=True)
    for n, (label, color, r) in enumerate(items):
        draw(r, n, color)
    axs[2].axvline(0, color=GRID, lw=0.8)
    # x-limits from data within the visible height range, ignoring the
    # lowest 100 m (strong surface-layer shear would squash everything else)
    z_lo, z_hi = limits.get("z") or (0.1, zmax)  # fit x to the heights in view
    for ax in axs:
        xs = []
        for line in ax.get_lines():
            xd, yd = np.asarray(line.get_xdata(), float), np.asarray(line.get_ydata(), float)
            s = (yd <= z_hi) & (yd >= z_lo) & np.isfinite(xd)
            if s.any() and xd.size > 2:
                xs += [xd[s].min(), xd[s].max()]
        if xs:
            lo, hi = min(xs), max(xs)
            pad = 0.06 * (hi - lo or 1.0)
            ax.set_xlim(lo - pad, hi + pad)

    # legends: which colour/style is which quantity, and which line is which sounding
    def qh(key, label, ls):
        return Line2D([], [], color=TEXT if by_color else qcol[key], lw=lk["prof_lw"], ls=ls,
                      label=label)
    _legend(axs[2], [qh("ws", "streamwise", "-"),
                     qh("wc", "crosswise", ":" if by_color else "-")], "upper right", fontsize=7)
    _legend(axs[4], [qh("th", "θ", "-"), qh("the", "θe", ":" if by_color else "-")],
            "upper left", fontsize=7)
    if not single or base is not None:
        hs = _sounding_handles(items, style if not single else "lines", base)
        leg = fig.legend(handles=hs, loc="upper right", ncol=len(hs), fontsize=7.5,
                         frameon=False, labelcolor=TEXT, handlelength=2.6,
                         bbox_to_anchor=(0.99, 1.0))
        leg.set_in_layout(False)
    if limits.get("z"):
        axs[0].set_ylim(*limits["z"])
    for i, xl in (limits.get("x") or {}).items():
        axs[int(i)].set_xlim(*xl)
    fig.cv_axes = {f"prof{i}": a for i, a in enumerate(axs)}
    return fig


# ------------------------------------------------------------ table
def _f(v, fmt="{:.0f}"):
    return "–" if v is None or not np.isfinite(v) else fmt.format(v)


THRESH = {  # value at which a cell is highlighted
    "SBCAPE": 1000, "MLCAPE": 1000, "MUCAPE": 1500, "0–3 km CAPE": 100,
    "0–1 km SRH": 150, "0–3 km SRH": 250, "Effective SRH": 150, "STP (fixed)": 1,
    "STP (effective)": 1, "SCP": 4,
}


def param_rows(r, units):
    """(name, value, units[, fmt[, (alt value, alt units, alt fmt)]]) rows; the alt is
    the same level as a pressure (hPa), shown when the row is toggled."""
    wf = _wfac(units)
    sb, ml, mu, kin, comp, th = r["sb"], r["ml"], r["mu"], r["kin"], r["comp"], r["thermo"]
    eil = kin["eil"]
    mag = lambda vec: np.hypot(*vec) * wf  # noqa: E731
    pr = r["prof"]

    def hpa(z):
        if z is None or not np.isfinite(z):
            return np.nan
        return float(np.exp(np.interp(z, pr["z"], np.log(pr["p"])))) / 100.0

    def lvl(name, z):
        return (name, z, "m", "{:.0f}", (hpa(z), "hPa", "{:.0f}"))

    return [
        ("Thermodynamics", None, None),
        ("SBCAPE", sb["cape"], "J/kg"), ("SBCIN", sb["cin"], "J/kg"),
        lvl("SB LCL", sb["lcl_z"]),
        ("MLCAPE", ml["cape"], "J/kg"), ("MLCIN", ml["cin"], "J/kg"),
        lvl("ML LCL", ml["lcl_z"]), lvl("ML LFC", ml["lfc_z"]), lvl("ML EL", ml["el_z"]),
        ("MUCAPE", mu["cape"], "J/kg"), lvl("MU parcel", pr["z"][mu["k0"]]),
        ("0–3 km CAPE", sb["cape3"], "J/kg"),
        ("0–3 km lapse rate", th["lr03"], "K/km", "{:.1f}"),
        ("700–500 hPa lapse rate", th["lr75"], "K/km", "{:.1f}"),
        ("Precipitable water", th["pw"], "mm", "{:.1f}"),
        lvl("Freezing level", th["frz"]),
        ("Sfc T / Td", (th["sfc_T"] - 273.15, th["sfc_Td"] - 273.15), "°C", "pair"),
        ("Sfc θe", th["sfc_the"], "K", "{:.1f}"),
        ("Kinematics", None, None),
        ("0–1 km shear", mag(kin["shear01"]), units),
        ("0–3 km shear", mag(kin["shear03"]), units),
        ("0–6 km shear", mag(kin["shear06"]), units),
        ("0–8 km shear", mag(kin["shear08"]), units),
        ("0–500 m SRH", kin["srh500"], "m²/s²"),
        ("0–1 km SRH", kin["srh1"], "m²/s²"),
        ("0–3 km SRH", kin["srh3"], "m²/s²"),
        ("Effective inflow", (eil[0], eil[1]), "m", "range",
         ((hpa(eil[0]), hpa(eil[1])), "hPa", "range")),
        ("Effective SRH", kin["esrh"], "m²/s²"),
        ("Effective bulk shear", kin["ebwd"] * wf, units),
        ("Bunkers RM", ("dir", kin["rm"]), units),
        ("Bunkers LM", ("dir", kin["lm"]), units),
        ("0–6 km mean wind", ("dir", kin["mean06"]), units),
        ("Storm motion used", ("dir", kin["storm"]), units),
        ("Sfc storm-rel. wind", kin["sr_sfc"] * wf, units),
        ("Critical angle", kin["crit"], "°"),
        ("Composites", None, None),
        ("STP (fixed)", comp["stp_fixed"], "", "{:.2f}"),
        ("STP (effective)", comp["stp_eff"], "", "{:.2f}"),
        ("SCP", comp["scp"], "", "{:.2f}"),
    ]


def _cell(val, fmt, units):
    if isinstance(val, tuple) and isinstance(val[0], str):  # ("dir", (u, v))
        return wind_dir_spd(val[1][0], val[1][1], units)
    if fmt == "range":
        return "none" if not np.isfinite(val[0]) else f"{val[0]:.0f} – {val[1]:.0f}"
    if fmt == "pair":
        return " / ".join(_f(x, "{:.1f}") for x in val)
    return _f(val, fmt)


def params_html(items, base=None, units="m/s"):
    """Two side-by-side tables: thermodynamics | kinematics + composites."""
    cols = list(items)
    if base is not None:
        cols.append(("Base", MUTED, base))
    rows = [param_rows(r, units) for _, _, r in cols]
    head = "".join(
        f'<th><span class="dot" style="background:{c}"></span>{lab}</th>' for lab, c, _ in cols)
    tables, body = [], []
    for i, row in enumerate(rows[0]):
        name = row[0]
        if row[1] is None and row[2] is None:
            if name == "Kinematics" and body:
                tables.append(body)
                body = []
            body.append(f'<tr class="sec"><td colspan="{len(cols) + 2}">{name}</td></tr>')
            continue
        fmt = row[3] if len(row) > 3 else "{:.0f}"
        alt = row[4] if len(row) > 4 else None
        tds = []
        for rr in rows:
            val = rr[i][1]
            hot = name in THRESH and isinstance(val, float) and np.isfinite(val) \
                and val >= THRESH[name]
            cell = _cell(val, fmt, units)
            if alt:  # both units in the cell; the row's toggle picks which is shown
                cell = (f'<span class="ua">{cell}</span>'
                        f'<span class="ub">{_cell(rr[i][4][0], alt[2], units)}</span>')
            tds.append(f'<td class="{"hot" if hot else ""}">{cell}</td>')
        if alt:
            body.append(f'<tr class="alt" data-row="{name}"><td class="pn">{name}</td>'
                        f'{"".join(tds)}<td class="u tog" title="Click: {row[2]} ↔ {alt[1]}">'
                        f'<span class="ua">{row[2]}</span><span class="ub">{alt[1]}</span>'
                        f' ⇄</td></tr>')
        else:
            body.append(f'<tr><td class="pn">{name}</td>{"".join(tds)}'
                        f'<td class="u">{row[2]}</td></tr>')
    tables.append(body)
    html = "".join(
        f'<table class="ptab"><thead><tr><th></th>{head}<th></th></tr></thead>'
        f'<tbody>{"".join(b)}</tbody></table>' for b in tables)
    return f'<div class="ptabs">{html}</div>'


# ------------------------------------------------------------ hover readout
# What the browser needs to read values off a drawn figure under the pointer: for each
# panel its frame (image fractions, y down), the affine map from image fractions to
# data coordinates (y in log p on the skew-T) and, per sounding, the profile arrays.
# The browser interpolates them at the pointer's height (or takes the nearest point of
# the hodograph), so hovering needs no round trip.
def _r(a, n=3):
    a = np.asarray(a, float)
    return [None if not np.isfinite(x) else round(float(x), n) for x in a]


def _frame(fig, ax):
    W, H = fig.bbox.width, fig.bbox.height
    b = ax.bbox
    return [b.x0 / W, 1.0 - b.y1 / H, b.x1 / W, 1.0 - b.y0 / H]


def _affine(fig, ax, ylog=False):
    """[[a, b, c], [d, e, f]]: data x = a fx + b fy + c, data y (log10 p if ylog) =
    d fx + e fy + f, from image fractions fx, fy (y down)."""
    W, H = fig.bbox.width, fig.bbox.height
    b = ax.bbox
    disp = np.array([(b.x0, b.y0), (b.x1, b.y0), (b.x0, b.y1)])
    dat = ax.transData.inverted().transform(disp)
    if ylog:
        dat[:, 1] = np.log10(dat[:, 1])
    A = np.column_stack([disp[:, 0] / W, 1.0 - disp[:, 1] / H, np.ones(3)])
    return [list(map(float, np.linalg.solve(A, dat[:, k]))) for k in (0, 1)]


def _soundings(items, base):
    out = [(label, color, r) for label, color, r in items]
    if base is not None:
        out.append(("Base state", MUTED, base))
    return out


def probe_skewt(fig, items, base=None, parcel="ml", units="m/s"):
    """Hover data of a skew-T / hodograph figure (see above)."""
    wf = _wfac(units)
    skew, hodo = fig.cv_axes["skew"], fig.cv_axes["hodo"]
    snd, hsnd = [], []
    for label, color, r in _soundings(items, base):
        pr = r["prof"]
        z = pr["z"] / 1000.0
        cols = [["z", "km AGL", 2, _r(z)], ["T", "°C", 1, _r(pr["T"] - 273.15, 2)],
                ["Td", "°C", 1, _r(pr["Td"] - 273.15, 2)]]
        if parcel in r:
            cols.append(["parcel", "°C", 1, _r(r[parcel]["T"] - 273.15, 2)])
        cols += [["RH", "%", 0, _r(pr["rh"], 1)], ["θ", "K", 1, _r(pr["th"], 2)],
                 ["θe", "K", 1, _r(pr["the"], 2)], ["qv", "g/kg", 1, _r(pr["qv"] * 1e3, 2)]]
        snd.append(dict(label=label, color=color, y=_r(np.log10(pr["p"] / 100.0), 5),
                        cols=cols, wind=[_r(pr["u"] * wf, 2), _r(pr["v"] * wf, 2)]))
        s = z <= _st(None)["hodo_top"] + 1.0
        d = hodo.transData.transform(np.column_stack([pr["u"][s] * wf, pr["v"][s] * wf]))
        W, H = fig.bbox.width, fig.bbox.height
        hsnd.append(dict(label=label, color=color, fx=_r(d[:, 0] / W, 4),
                         fy=_r(1.0 - d[:, 1] / H, 4), z=_r(z[s]),
                         wind=[_r(pr["u"][s] * wf, 2), _r(pr["v"][s] * wf, 2)]))
    return dict(units=units, panels=[
        dict(kind="y", name="skew", frame=_frame(fig, skew), aff=_affine(fig, skew, True),
             ylabel="p", yunit="hPa", ylog=True, xlabel="T", xunit="°C", snd=snd),
        dict(kind="xy", name="hodo", frame=_frame(fig, hodo), aff=_affine(fig, hodo),
             xlabel="u", ylabel="v", snd=hsnd)])


def probe_profiles(fig, items, base=None, units="m/s"):
    """Hover data of a profiles figure: one panel spanning the five (they share z)."""
    wf = _wfac(units)
    axs = [fig.cv_axes[f"prof{i}"] for i in range(len(PROFILE_PANELS))]
    fr = [_frame(fig, a) for a in axs]
    snd = []
    for label, color, r in _soundings(items, base):
        pf, pr = r["profiles"], r["prof"]
        zm, z = pf["zm"] / 1000.0, pf["z"] / 1000.0
        snd.append(dict(label=label, color=color, ys=dict(m=_r(zm, 4), z=_r(z, 4)), cols=[
            ["SR wind", units, 1, "m", _r(pf["sr_speed"] * wf, 2)],
            ["shear", "10⁻³ s⁻¹", 1, "m", _r(pf["shear"] * 1e3, 2)],
            ["ωs", "10⁻³ s⁻¹", 1, "m", _r(pf["ws"] * 1e3, 2)],
            ["ωc", "10⁻³ s⁻¹", 1, "m", _r(pf["wc"] * 1e3, 2)],
            ["SRH", "m²/s²", 0, "z", _r(pf["cum_srh"], 1)],
            ["θ", "K", 1, "z", _r(pr["th"], 2)], ["θe", "K", 1, "z", _r(pr["the"], 2)]]))
    frame = [min(f[0] for f in fr), min(f[1] for f in fr), max(f[2] for f in fr),
             max(f[3] for f in fr)]
    return dict(units=units, panels=[
        dict(kind="z", name="prof", frame=frame, frames=fr, aff=_affine(fig, axs[0]),
             ylabel="z", yunit="km AGL", snd=snd)])
