"""cm1view command-line entry point:  python -m cm1view RUN_DIR [options]

    cm1view render FIGURE [--run PATH ...] [options]   draws a saved figure or template
                                                      without the viewer (cm1view render -h)
    cm1view export RUN --fields A,B [options]         writes fields to netCDF without the
                                                      viewer (cm1view export -h)
    cm1view export RUN --parcels SET [options]        writes a saved parcel set's
                                                      trajectories to netCDF or CSV
    cm1view bench RUN [options]                       times the viewer's updates without
                                                      a browser (cm1view bench -h)"""

import argparse
import os
import socket
import sys
import time


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["render"]:  # (a run folder named "render": ./render)
        from .figures.batch import main as render
        return render(argv[1:])
    if argv[:1] == ["export"]:  # (likewise: ./export)
        from .core.export import main as export
        return export(argv[1:])
    if argv[:1] == ["bench"]:  # (likewise: ./bench)
        from .bench import main as bench
        return bench(argv[1:])
    ap = argparse.ArgumentParser(prog="cm1view", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?", default=None,
                    help="directory containing model output (default: the "
                         "default_run setting, else pick one in the browser)")
    from .core.models import AUTO, MODELS
    ap.add_argument("--model", default=AUTO, choices=[AUTO, *MODELS],
                    help="the model whose output RUN holds (default: auto, detected "
                         "from the files)")
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
    ap.add_argument("--demo", nargs="?", const="cm1", choices=("cm1", "wofs"), metavar="MODEL",
                    help="open synthetic demo runs, CM1 (the default) or wofs (written once "
                         "to the cache folder)")
    ap.add_argument("--address", default="127.0.0.1",
                    help="bind address (127.0.0.1 is right for JupyterHub and SSH tunnels)")
    ap.add_argument("--timing", nargs="?", const="auto", default=None, metavar="FILE",
                    help="log how long each map, sounding, cross-section and 3D update "
                         "takes, browser included, to FILE (default: timing-DATE.jsonl in "
                         "the cache folder); summary: cm1view bench --report FILE")
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
    if args.demo:
        from . import demo, demo_wofs
        root = os.path.join(config.expand(config.get("cache_dir")), "demo")
        print(f"cm1view: demo runs in {root}", flush=True)
        if args.demo == "wofs":
            args.run = demo_wofs.make(root)
            config.override("runs_root", [args.run], "--demo")
        else:
            args.run = demo.make(root)
            config.override("runs_root", [os.path.join(root, "demo")], "--demo")
    if config.read_error():
        print(f"cm1view: could not read the settings ({config.read_error()}); "
              "using defaults until they are saved again", flush=True)
    from .registry import Registry
    from .viewer.app import create_app
    import panel as pn

    cache, cache_how = config.cache_gb()
    workers, _ = config.workers()
    start = args.run or config.get("default_run") or None
    if start:
        start = config.expand(start)
    t0 = time.time()
    from .core import pool
    from .core.run import MAX_READERS
    pool.warm(min(workers, MAX_READERS))  # (the readers start while the run is opened)
    reg = Registry(start, cache, workers, model=args.model)
    if start:
        try:
            run, fields = reg.get()
            print(f"cm1view: {run.model_label}, {len(run.times)} times, "
                  f"{run.ni}x{run.nj}x{run.nk}, "
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

    if args.timing:
        from .viewer import timing
        path = args.timing
        if path == "auto":
            path = config.cache_dir("timing", time.strftime("timing-%Y%m%d-%H%M%S.jsonl"))
        path = timing.start(path, reg.get()[0] if start and reg.default else None)
        print(f"cm1view: timing every update into {path}\n"
              f"         (keep the tab in front; summary: cm1view bench --report {path})",
              flush=True)
    port = _free_port(config.get("port"), args.address)
    host, user = socket.getfqdn(), os.environ.get("USER", "you")
    print("\nOpen the viewer:", flush=True)
    print(f"  This machine:  http://localhost:{port}/cm1view")
    prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX")
    if prefix:
        hub = (os.environ.get("JUPYTERHUB_PUBLIC_URL")
               or os.environ.get("JUPYTERHUB_PUBLIC_HUB_URL", "").removesuffix("hub/"))
        hub = hub.rstrip("/") if hub else "https://<your JupyterHub>"
        print(f"  JupyterHub:    {hub}{prefix}proxy/{port}/cm1view")
    in_job = os.environ.get("PBS_JOBID") or os.environ.get("SLURM_JOB_ID")
    if in_job or os.environ.get("SSH_CONNECTION"):
        login = config.get("login_host") or config.submit_host() or "<login-host>"
        hop = f"-J {user}@{login} {user}@{host}" if in_job else f"{user}@{host}"
        print(f"  SSH tunnel:    ssh -N -L {port}:localhost:{port} {hop}")
        print(f"                 then open http://localhost:{port}/cm1view")
    print(flush=True)
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
