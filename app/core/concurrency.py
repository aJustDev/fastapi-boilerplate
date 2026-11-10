import functools
from collections.abc import Callable

import anyio


async def run_blocking[T](func: Callable[..., T], *args: object, **kwargs: object) -> T:
    """Run a blocking, CPU-bound function in the thread pool.

    The event loop is single-threaded: an argon2 hash (64 MiB, tens of milliseconds) run
    inline stalls every other request of the worker while it computes.
    """
    return await anyio.to_thread.run_sync(functools.partial(func, *args, **kwargs))
