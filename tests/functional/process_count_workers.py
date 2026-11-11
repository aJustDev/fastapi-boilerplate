"""Three workers started the way uvicorn starts its own, each saying how many it counts.

Run as a process of its own (`python -m tests.functional.process_count_workers`), so that the
workers are the only children of their parent: `test_process_count.py` reads what it prints.
"""

import multiprocessing
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event

from app.core.startup import _count_sibling_workers

WORKERS = 3


def _report(all_started: Event, counts: Queue[int]) -> None:
    all_started.wait(20)
    counts.put(_count_sibling_workers())


def main() -> None:
    spawn = multiprocessing.get_context("spawn")  # uvicorn's, for --workers and --reload
    all_started, counts = spawn.Event(), spawn.Queue()
    workers = [spawn.Process(target=_report, args=(all_started, counts)) for _ in range(WORKERS)]
    for worker in workers:
        worker.start()
    all_started.set()
    print(sorted(counts.get(timeout=30) for _ in workers))
    for worker in workers:
        worker.join(timeout=10)


if __name__ == "__main__":
    main()
