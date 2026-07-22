"""Parallel execution helpers for batch LLM workloads."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable, Iterator, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def parallel_map(
    func: Callable[[object], T],
    items: Iterable,
    max_workers: int = 4,
) -> Iterator[tuple[object, T | Exception]]:
    """Map *func* over *items* in parallel, yielding ``(item, result)`` as
    each future completes.

    If *func* raises, the exception is yielded as the result so the caller
    can decide whether to abort or continue.

    Usage::

        for item, result in parallel_map(process, samples, max_workers=4):
            if isinstance(result, Exception):
                print(f"Error on {item}: {result}")
            else:
                print(f"OK: {item} -> {result}")
    """
    if not items:
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {executor.submit(func, item): item for item in items}
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                yield (item, future.result())
            except Exception as exc:
                yield (item, exc)


def atomic_write(
    lock: threading.Lock,
    fn: Callable[[], None],
) -> None:
    """Execute *fn* while holding *lock* — a tiny scope guard for shared writes."""
    with lock:
        fn()
