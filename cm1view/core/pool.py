"""The reader processes: one pool for the whole program.

Every run reads its 3D fields here (core.run), and the work done one output time (or
one frame) at a time uses the same processes: time series (core.series), animation
frames (figures.anim), the first scan of a run's files, the inputs of the pressure
decomposition.  So the `workers` setting is the CPU budget: no more than that many
processes are busy however many runs and tools are at work, and nothing waits for
processes of its own to start.

A reader keeps the last few output files it read open (core.run.opened); release()
has every reader close them, before a file is written to.
"""

import threading

KEEP_OPEN = 3  # output files a reader keeps open
RELEASE_WAIT = 15.0  # s release() waits for the readers at most

_lock = threading.Lock()
_ex = None  # the pool
_size = 0  # its processes
_barrier = None  # release(): holds each reader until all have closed their files
_reader_barrier = None  # (in a reader process: the same barrier)


def _init(barrier):
    """In a reader process, once: what every task needs, loaded before the first one."""
    global _reader_barrier
    _reader_barrier = barrier
    import netCDF4

    from . import run
    run.KEEP_OPEN = KEEP_OPEN
    try:
        # a reader reads each chunk once: HDF5's chunk cache (tens of MB a variable of
        # every file kept open) would only hold memory
        netCDF4.set_chunk_cache(0)
    except Exception:  # noqa: BLE001
        run.KEEP_OPEN = 0  # (then no file stays open with its cache)


def _usable(ex):
    return not (getattr(ex, "_broken", False) or getattr(ex, "_shutdown_thread", False))


def get(workers):
    """The pool, of at least `workers` processes (started as tasks need them: warm()
    starts them all).  A larger one replaces it when more are asked for than it has,
    and a new one when a reader died (out of memory); the old one finishes the tasks it
    was given and goes when nothing holds it any more, so do not keep it."""
    global _ex, _size, _barrier
    workers = max(1, int(workers))
    with _lock:
        if _ex is None or _size < workers or not _usable(_ex):
            import multiprocessing as mp
            from concurrent.futures import ProcessPoolExecutor

            ctx = mp.get_context("spawn")
            _barrier = ctx.Barrier(workers)
            _ex = ProcessPoolExecutor(max_workers=workers, mp_context=ctx,
                                      initializer=_init, initargs=(_barrier,))
            _size = workers
        return _ex


def close():
    """Stop the reader processes (a program about to end; the next read starts new
    ones).  Tasks not started are dropped."""
    global _ex
    with _lock:
        ex, _ex = _ex, None
    if ex is not None:
        ex.shutdown(wait=True, cancel_futures=True)


def size():
    """Processes of the pool (0: none yet)."""
    with _lock:
        return _size if _ex is not None else 0


def _nothing():
    return None


def warm(workers):
    """Start the pool's processes now, in the background, so that the first read does
    not wait for them (about a second each: Python, numpy and netCDF to load)."""
    if int(workers) > 1:
        ex = get(workers)
        for _ in range(int(workers)):  # (none is idle yet: each task starts a process)
            ex.submit(_nothing)


def width(workers):
    """How many of `workers` readers the work of a whole run of times (a series,
    animation frames) keeps busy at once: a quarter stays free for the reads of the
    page."""
    workers = max(1, int(workers))
    return max(1, workers - workers // 4)


def spread(ex, fn, items, width):
    """fn(item) of every item in the pool `ex`, at most `width` at a time: yields the
    results as they complete.  Closing the generator drops the items not started."""
    from concurrent.futures import FIRST_COMPLETED, wait

    items, live, more = iter(items), set(), True
    try:
        while True:
            while more and len(live) < max(1, width):
                try:
                    live.add(ex.submit(fn, next(items)))
                except StopIteration:
                    more = False
            if not live:
                return
            done, live = wait(live, return_when=FIRST_COMPLETED)
            for f in done:
                yield f.result()
    finally:
        for f in live:
            f.cancel()


def _release(timeout):
    """In a reader process: close the files kept open, then wait for the other readers
    to do the same (so that every reader takes one of these tasks)."""
    from . import run
    run.close_kept()
    try:
        _reader_barrier.wait(timeout)
    except threading.BrokenBarrierError:
        pass


def release(timeout=RELEASE_WAIT):
    """Have every reader close the output files it keeps open, so that one of them can
    be opened for writing.  Waits for the readers to finish what they are on, at most
    `timeout` s (then goes on: a reader still busy closes its files when it is done)."""
    from concurrent.futures import wait

    with _lock:
        ex, n, barrier = _ex, _size, _barrier
    if ex is None or not _usable(ex):
        return
    try:
        barrier.reset()
        wait([ex.submit(_release, timeout) for _ in range(n)], timeout + 2.0)
    except Exception:  # noqa: BLE001
        pass
