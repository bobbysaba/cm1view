"""cm1view command-line entry point:  python -m cm1view RUN_DIR [options]"""

import argparse
import os
import socket
import sys
import time


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cm1view", description=__doc__)
    ap.add_argument("run", help="directory containing cm1out_NNNNNN.nc files")
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--cache-gb", type=float, default=None,
                    help="memory budget for cached 3D fields (default: ~40%% of the job's "
                         "memory, max 48)")
    ap.add_argument("--workers", type=int, default=None,
                    help="parallel reader processes (default: CPUs in this job, max 8)")
    ap.add_argument("--maxpix", type=int, default=900,
                    help="max map pixels sent per axis (zoom in for full resolution)")
    ap.add_argument("--address", default="127.0.0.1",
                    help="bind address (127.0.0.1 is right for JupyterHub and SSH tunnels)")
    args = ap.parse_args(argv)

    from .registry import Registry
    from .app import create_app
    import panel as pn

    cache = args.cache_gb if args.cache_gb is not None else _default_cache_gb()
    t0 = time.time()
    reg = Registry(args.run, cache, args.workers)
    run, fields = reg.get()
    print(f"cm1view: {len(run.files)} files, {run.ni}x{run.nj}x{run.nk}, "
          f"{len(fields.defs)} fields, cache {cache:.0f} GB, {run.workers} reader(s) "
          f"[{time.time() - t0:.1f}s]", flush=True)

    host, user, port = socket.gethostname().split(".")[0], os.environ.get("USER", "you"), args.port
    prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX")
    print("\nOpen the viewer:", flush=True)
    if prefix:
        print(f"  JupyterHub:  https://jupyterhub.hpc.ucar.edu{prefix}proxy/{port}/cm1view")
    else:
        print(f"  JupyterHub:  https://jupyterhub.hpc.ucar.edu/stable/user/{user}/proxy/"
              f"{port}/cm1view   (if this job was started from JupyterHub)")
    print(f"  SSH tunnel:  ssh -N -L {port}:localhost:{port} -J {user}@casper.ucar.edu "
          f"{user}@{host}")
    print(f"               then open http://localhost:{port}/cm1view\n", flush=True)
    print("Switch runs from the viewer header, or add ?run=/path/to/run to the URL.\n",
          flush=True)

    def session():  # one Viewer per browser session; runs (and their caches) are shared
        return create_app(reg, args.maxpix)

    pn.serve({"cm1view": session},
             port=port, address=args.address, show=False, title="CM1 View",
             allow_websocket_origin=["*"], websocket_max_message_size=512 * 1024 * 1024,
             check_unused_sessions=5000, unused_session_lifetime=30000)


def _default_cache_gb():
    limit = None
    for f in ("/sys/fs/cgroup/memory.max",):
        try:
            v = open(f).read().strip()
            limit = None if v == "max" else int(v)
        except OSError:
            pass
    if limit is None or limit > 1 << 50:
        try:  # cgroup v1 (Casper)
            cg = [line.split(":")[2].strip() for line in open("/proc/self/cgroup")
                  if ":memory:" in line][0]
            limit = int(open(f"/sys/fs/cgroup/memory{cg}/memory.limit_in_bytes").read())
        except (OSError, IndexError, ValueError):
            limit = None
    if limit is None or limit > 1 << 50:
        limit = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return float(max(2.0, min(48.0, 0.4 * limit / 1024**3)))


if __name__ == "__main__":
    sys.exit(main())
