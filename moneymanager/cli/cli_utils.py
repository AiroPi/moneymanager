from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from functools import wraps
from typing import Annotated, Any

import typer

from ..loaders import (
    load_cache,
    save_data,
)

BeforeOption = Annotated[
    datetime | None, typer.Option(help="Exclude transactions after this date (the date itself is excluded)")
]
AfterOption = Annotated[
    datetime | None, typer.Option(help="Exclude transactions prior to this date (the date itself is included)")
]


def path_autocomplete(
    file_okay: bool = True,
    dir_okay: bool = True,
    writable: bool = False,
    readable: bool = True,
    allow_dash: bool = False,
    match_wildcard: str | None = None,
) -> Callable[[str], list[str]]:
    def wildcard_match(string: str, pattern: str) -> bool:
        regex = re.escape(pattern).replace(r"\?", ".").replace(r"\*", ".*")
        return re.fullmatch(regex, string) is not None

    def completer(incomplete: str) -> list[str]:
        items = os.listdir()
        completions: list[str] = []
        for item in items:
            if (not file_okay and os.path.isfile(item)) or (not dir_okay and os.path.isdir(item)):
                continue

            if readable and not os.access(item, os.R_OK):
                continue
            if writable and not os.access(item, os.W_OK):
                continue

            completions.append(item)

        if allow_dash:
            completions.append("-")

        if match_wildcard is not None:
            completions = filter(lambda i: wildcard_match(i, match_wildcard), completions)  # type: ignore

        return [i for i in completions if i.startswith(incomplete)]

    return completer


type CommandCb[**P, R] = Callable[P, R]
type SimpleFunctions = Iterable[Callable[[], Any]]


def with_operation_wrappers(*, before: SimpleFunctions | None = None, after: SimpleFunctions | None = None):
    def decorator[R, **P](f: CommandCb[P, R]) -> CommandCb[P, R]:
        @wraps(f)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            if before:
                for callable in before:
                    callable()
            result = f(*args, **kwargs)
            if after:
                for callable in after:
                    callable()
            return result

        return wrapped

    return decorator


with_load = with_operation_wrappers(before=[load_cache])
"""
Decorator to use if a command need the cache to be loaded to be executed.

`typer.Context` must be the first argument of the command callback.
The decorator must be placed under the `Typer.command()` decorator (in order to be executed before).

Example:
```py
@app.command()
@with_load()
def my_command(ctx: typer.Context):
    ...
```
"""


with_load_and_save = with_operation_wrappers(before=[load_cache], after=[save_data])
"""
Same than `with_load()` but save at the end of the function also.
"""
