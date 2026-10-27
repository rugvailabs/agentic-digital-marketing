"""Who is allowed to spend the last of the day's budget.

A scheduled curate runs unattended at 12:45 and a user clicking "Generate
post" is sitting there waiting. On a free tier of 20 calls per model per day
those two compete, and without this the curate wins simply by running first:
it would take the whole allowance at lunchtime and every Desk action for the
rest of the day would fail with "no model answered".

So background work stops a few calls early and the Desk gets the rest.

A context variable rather than an argument on `generate_json`, because the
caller that knows is the Celery task and the code that needs to know is
inside the provider, four layers down. Threading a flag through every
signature in between would put scheduling policy into the LLM interface,
which has no business with it.

`contextvars` is the right mechanism and not `threading.local`: each Celery
task runs its own `asyncio.run()` loop, and a context variable set inside a
coroutine is visible to everything it awaits and to nothing it does not.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

#: True while the current task is scheduled work rather than a user waiting.
_background: ContextVar[bool] = ContextVar("llm_background", default=False)


@contextmanager
def background() -> Iterator[None]:
    """Mark everything inside as deferrable work.

    Wrap a scheduled task, never a request handler. The Desk is the default
    for the same reason errors are: the common case should need no
    ceremony, and forgetting this costs freshness rather than a failure a
    user can see.
    """
    token = _background.set(True)
    try:
        yield
    finally:
        _background.reset(token)


def is_background() -> bool:
    """Whether the current call is scheduled work."""
    return _background.get()
