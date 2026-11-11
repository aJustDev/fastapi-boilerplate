def one_line(exc: BaseException) -> str:
    """An exception in one line: `ConnectTimeout`, `ValueError: bad input`.

    For a log line that leaves the traceback out: a failure that repeats (a retry, a
    probe, a reconnection) is told in one line each time, not in forty.
    """
    message = " ".join(str(exc).split())
    if len(message) > 200:
        message = message[:197] + "..."
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
