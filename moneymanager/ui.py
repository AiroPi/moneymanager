from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markdown import Markdown as Markdown
from rich.prompt import Confirm as Confirm
from rich.table import Table as Table
from rich.text import Text as Text

if TYPE_CHECKING:
    from decimal import Decimal

    from .transaction import Transaction

console = Console()


def transactions_table(transactions: Iterable[Transaction]):
    table = Table(show_footer=True, width=console.width)
    table.add_column("date")
    table.add_column("bank")
    table.add_column("account")
    table.add_column("label", footer=Text.from_markup("[b]Total", justify="right"))
    table.add_column("amount", justify="right")

    total = 0
    for tr in transactions:
        table.add_row(tr.date.strftime("%Y-%m-%d"), tr.bank.name, tr.account.alias, tr.label, format_amount(tr.amount))
        total += tr.amount

    table.columns[4].footer = format_amount(total)

    return table


def format_amount(amount: float | Decimal):
    color = "[red]" if amount < 0 else "[green]"
    return f"{color}{amount:,.2f}€"
