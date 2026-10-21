"""cm1view command-line entry point:  python -m cm1view RUN_DIR [options]"""

import argparse
import os
import socket
import sys
import time


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cm1view", description=__doc__)
    ap.add_argument("run", nargs="?", default=None,
                    help="directory containing CM1 output files (default: the "
                         "default_run setting, else pick one in the browser)")
    ap.add_argument("--config", default=None,
                    help="settings file (default: $CM1VIEW_CONFIG, else "
                         "~/.config/cm1view/config.toml)")
    ap.add_argument("--port", type=int, default=None,
                    help="server port (default: the port setting, 5006; the next free "
                         "port is used if it is taken)")
    ap.add_argument("--cache-gb", type=float, default=None,
                    help="memory budget for cached 3D fields (default: ~40%% of the job's "
                         "memory, max 48)")
    ap.add_argument("--workers", type=int, default=None,
                    help="parallel reader processes (default: CPUs in this job, max 8)")
    ap.add_argument("--maxpix", type=int, default=None,
                    help="max map pixels sent per axis (zoom in for full resolution)")
    ap.add_argument("--pdecomp-script", default=None,
                    help="pressure-decomposition script run for times whose files lack "
                         "p_b/p_l/p_nl (default: the pdecomp_script setting)")
    ap.add_argument("--address", default="127.0.0.1",
                    help="bind address (127.0.0.1 is right for JupyterHub and SSH tunnels)")
    args = ap.parse_args(argv)

    from . import config
    if args.config:
        config.load(args.config)
    for name, flag in (("port", "--port"), ("cache_gb", "--cache-gb"),
                       ("workers", "--workers"), ("maxpix", "--maxpix"),
                       ("pdecomp_script", "--pdecomp-script")):
        val = getattr(args, name)
        if val is not None:
            config.override(name, val, flag)
    if config.read_error():
        print(f"cm1view: could not read the settings ({config.read_error()}); "
              "using defaults until they are saved again", flush=True)
    from .registry import Registry
    from .app import create_app
    import panel as pn

    cache, cache_how = config.cache_gb()
    workers, _ = config.workers()
    start = args.run or config.get("default_run") or None
    if start:
        start = config.expand(start)
    t0 = time.time()
    reg = Registry(start, cache, workers)
    if start:
        try:
            run, fields = reg.get()
            print(f"cm1view: {len(run.files)} files, {run.ni}x{run.nj}x{run.nk}, "
                  f"{len(fields.defs)} fields, cache {cache:.0f} GB, {run.workers} "
                  f"reader(s) [{time.time() - t0:.1f}s]", flush=True)
        except Exception as e:  # noqa: BLE001
            if args.run:
                raise
            print(f"cm1view: default_run {start} could not be opened ({e}); pick a run "
                  "in the browser", flush=True)
            reg.default = None
    else:
        print(f"cm1view: no run given, pick one in the browser (cache {cache:.0f} GB, "
              f"{cache_how})", flush=True)
    if config.needs_setup():
        print(f"cm1view: first run: the browser asks for your settings "
              f"({config.config_path()})", flush=True)

    port = _free_port(config.get("port"), args.address)
    host, user = socket.gethostname().split(".")[0], os.environ.get("USER", "you")
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
        return create_app(reg)

    pn.serve({"cm1view": session},
             port=port, address=args.address, show=False, title="CM1 View",
             allow_websocket_origin=["*"], websocket_max_message_size=512 * 1024 * 1024,
             check_unused_sessions=5000, unused_session_lifetime=30000)


def _free_port(port, address):
    """`port`, or the next free one above it (another user may have it on this node)."""
    for p in range(port, port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((address, p))
            except OSError:
                continue
        if p != port:
            print(f"cm1view: port {port} is taken, using {p}", flush=True)
        return p
    return port


if __name__ == "__main__":
    sys.exit(main())
