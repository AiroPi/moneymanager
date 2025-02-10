from __future__ import annotations

from typing import TYPE_CHECKING, cast

import typer

from ..cli.cli_utils import with_load
from ..ui import (
    Markdown,
    Panel,
    Pretty,
    console,
)
from . import (
    cache,
)

if TYPE_CHECKING:
    from ..group import AutoGroupRuleSets


debug_subcommands = typer.Typer(hidden=True, no_args_is_help=True)


@debug_subcommands.command(name="auto-group")
@with_load
def debug_auto_group(transaction_id: str):
    """
    Debugs the auto grouping for a specific transaction.
    """
    transaction = next((t for t in cache.transactions if t.id == transaction_id), None)
    if transaction is None:
        raise ValueError("Transaction not found.")

    console.print(Markdown(f"Testing against transaction {transaction_id}"))
    console.print(Panel(Pretty(transaction)))

    groups_with_rules = [g for g in cache.groups.all() if g.rules]
    for i, group in enumerate(groups_with_rules):
        if TYPE_CHECKING:
            group.rules = cast(AutoGroupRuleSets, group.rules)
        result = "[green]PASSED" if group.rules.test_match(transaction) else "[red]FAILED"
        console.print(f"[bold]Test {i + 1}/{len(groups_with_rules)} ({group.name}): [/bold] {result}")
        console.print(Panel(Pretty(group.rules), title="Rules"))
