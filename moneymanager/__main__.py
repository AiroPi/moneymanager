from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Annotated
from urllib import request

import typer
from pydantic_core import from_json
from rich.columns import Columns
from rich.console import Group as RichGroup
from rich.markdown import Markdown
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from moneymanager import (
    cache,
    filter_helper,
)
from moneymanager.autogroup import prompt_automatic_grouping
from moneymanager.loaders import PathsOptions, get_reader, load_cache, save_data
from moneymanager.ui import console, format_amount, transactions_table

if TYPE_CHECKING:
    from moneymanager.group import Group

app = typer.Typer(no_args_is_help=True)
debug_subcommands = typer.Typer(hidden=True, no_args_is_help=True)
app.add_typer(debug_subcommands, name="debug", help="Debug commands.")
reader_subcommands = typer.Typer(no_args_is_help=True, help="Commands related to readers.")
app.add_typer(reader_subcommands, name="reader")

BeforeOption = Annotated[
    datetime | None, typer.Option(help="Exclude transactions after this date (the date itself is excluded)")
]
AfterOption = Annotated[
    datetime | None, typer.Option(help="Exclude transactions prior to this date (the date itself is included)")
]


@app.callback()
def common(
    ctx: typer.Context,
    readers: Path = typer.Option(Path("./readers"), envvar="READERS_PATH", help="Path to the readers files folder."),
    exports: Path = typer.Option(
        Path("./exports"), envvar="EXPORTS_PATH", help="Path to the transactions exports folder."
    ),
    rules: Path = typer.Option(Path("./auto_group.yml"), envvar="RULES_PATH", help="Path to the autogroup rules."),
    groups: Path = typer.Option(Path("./groups.yml"), envvar="GROUPS_PATH", help="Path to the groups definitions."),
    settings: Path = typer.Option(
        Path("./accounts_settings.yml"), envvar="SETTINGS_PATH", help="Path to the account settings."
    ),
    debug: bool = typer.Option(False, help="Show some debug values"),
):
    ctx.obj = SimpleNamespace(paths=PathsOptions(readers, exports, rules, groups, settings), debug=debug)
    if debug:
        cache.debug_mode = debug


@app.command()
def categories(
    ctx: typer.Context,
    show_empty: Annotated[bool, typer.Option(help="Show categories with 0 transactions.")] = False,
    before: BeforeOption = None,
    after: AfterOption = None,
):
    """
    Shows a tree view of your expenses grouped by categories.
    """
    load_cache(ctx.obj.paths)
    filter = filter_helper(before, after)
    console.print(Markdown("# By category"))

    categories_table = Table(show_header=True, header_style="bold", width=console.width)
    categories_table.add_column("Category")
    categories_table.add_column("Total", justify="right")
    categories_table.add_column("Number", justify="right")

    def build_tree_table(_groups: Iterable[Group], tree: Tree | None = None, table: Table | None = None):
        if tree is None:
            tree = Tree("[b]groups")
        if table is None:
            table = Table(show_header=True, box=None)
            table.add_column("amount", justify="right")
            table.add_column("nb", justify="right")

        for group in _groups:
            value = sum(tr.amount for tr in filter(group.all_transactions))
            number = len(list(filter(group.all_transactions)))
            if number == 0 and not show_empty:  # value is 0 if number is 0
                continue

            bold = "[b]" if group.subgroups else ""
            leaf = tree.add(f"{bold}{group.name}")

            table.add_row(format_amount(value), str(number))
            if group.subgroups:
                build_tree_table(group.subgroups, leaf, table)
        return table, tree

    table, tree = build_tree_table(cache.groups)

    console.print(Columns([table, RichGroup("[bold]groups", *tree.children)]))


@app.command()
def transactions(
    ctx: typer.Context,
    before: BeforeOption = None,
    after: AfterOption = None,
):
    """
    Lists all your transactions.
    """
    load_cache(ctx.obj.paths)
    filter = filter_helper(before, after)

    table = transactions_table(sorted(filter(cache.transactions), key=lambda tr: tr.date))
    console.print(table)


@app.command()
def accounts(ctx: typer.Context):
    """
    Shows a recap of your accounts state.
    """
    load_cache(ctx.obj.paths)

    console.print(Markdown("# Accounts"))
    accounts_table = Table(show_header=True, header_style="bold", width=console.width)
    accounts_table.add_column("Bank")
    accounts_table.add_column("Account", Text.from_markup("[b]Total", justify="right"))
    accounts_table.add_column("Value", justify="right")
    accounts_table.show_footer = True

    total = 0
    for bank in cache.banks:
        for account in bank.accounts:
            value = sum(Decimal(tr.amount) for tr in account.transactions)
            value += cache.accounts_settings.initial_values.get(bank.name, {}).get(account.name, 0)

            total += value

            accounts_table.add_row(
                bank.name,
                cache.accounts_settings.aliases.get(bank.name, {}).get(account.name, account.name),
                f"{value:,.2f}€",
            )

    accounts_table.columns[2].footer = f"[u]{total:,.2f}€"

    console.print(accounts_table)


@reader_subcommands.command(name="install-defaults")
def reader_install_defaults(path: Path = Path("./readers")):
    """
    Installs the default readers available at https://github.com/AiroPi/moneymanager/tree/master/readers.
    """
    if not path.exists():
        path.mkdir()

    with request.urlopen("https://api.github.com/repos/AiroPi/moneymanager/contents/readers?ref=master") as response:
        files = from_json(response.read())

    for file in files:
        with request.urlopen(file["download_url"]) as response, (path / file["name"]).open("wb+") as f:  # noqa: S310
            f.write(response.read())
        print(f"{file["name"]} downloaded successfully.")

    print("Readers downloaded successfully.")


@reader_subcommands.command(name="instructions")
def reader_instructions(
    reader_path: Annotated[Path, typer.Argument(help="The reader you want instruction from.")],
):
    """
    Gets the instructions to use a specific reader (how to make the transactions export).
    """
    try:
        reader = get_reader(reader_path)
    except ValueError:
        console.print_exception()
        return
    if reader.__doc__ is None:
        console.print("No instructions found for this reader.")
        return
    console.print(Markdown(reader.__doc__))


@debug_subcommands.command(name="auto-group")
def debug_auto_group(ctx: typer.Context, transaction_id: str):
    """
    Debugs the auto grouping for a specific transaction.
    """
    load_cache(ctx.obj.paths)
    transaction = next((t for t in cache.transactions if t.id == transaction_id), None)
    if transaction is None:
        raise ValueError("Transaction not found.")

    console.print(Markdown(f"Testing against transaction {transaction_id}"))
    console.print(Panel(Pretty(transaction)))

    for i, grouping_rule in enumerate(cache.grouping_rules):
        result = "[green]PASSED" if grouping_rule.test_match(transaction) else "[red]FAILED"
        console.print(f"[bold]Test {i+1}/{len(cache.grouping_rules)} ({grouping_rule.group.name}): [/bold] {result}")
        console.print(Panel(Pretty(grouping_rule.rules), title="Rules"))


@app.command()
def apply_auto_group(ctx: typer.Context):
    """
    Manually apply automatic grouping.
    """
    load_cache(ctx.obj.paths)
    infos = prompt_automatic_grouping()
    save_data()
    if infos.groups_updated == 0:
        console.print("Not any group to update.")
        return
    plural = "different" if infos.groups_updated > 1 else "single"
    console.print(
        f"Found [bold]{infos.binds_added}[/bold] groups to add, [bold]{infos.binds_removed}[/bold] groups "
        f"to remove, for [bold]{infos.groups_updated}[/bold] {plural} [default not bold]group(s)."
    )
    # todo


if __name__ == "__main__":
    typer.run(app)
