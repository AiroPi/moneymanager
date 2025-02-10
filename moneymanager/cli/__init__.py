from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from ..autogroup import prompt_automatic_grouping
from ..cache import cache
from ..filters import filter_helper
from ..loaders import (
    MoneymanagerPaths,
    import_transactions_export,
    init_cache,
    init_paths,
)
from ..ui import (
    Columns,
    Group as RichGroup,
    Markdown,
    Table,
    Text,
    Tree,
    console,
    format_amount,
    transactions_table,
)
from .cli_utils import AfterOption, BeforeOption, path_autocomplete, with_load, with_load_and_save
from .debug import debug_subcommands
from .grafana import grafana_subcommands
from .manage import manage_subcommands
from .reader import reader_subcommands
from .update import update_subcommands

if TYPE_CHECKING:
    from ..group import Group
    from ..transaction import Transaction


app = typer.Typer(no_args_is_help=True)
app.add_typer(debug_subcommands, name="debug", help="Debug commands.")
app.add_typer(reader_subcommands, name="reader")
app.add_typer(manage_subcommands, name="manage")
app.add_typer(update_subcommands, name="update")
app.add_typer(grafana_subcommands, name="grafana")


@app.callback()
def common(
    ctx: typer.Context,
    moneymanager_path: Path = typer.Option(
        Path("."),
        envvar="MONEYMANAGER_PATH",
        help="Location of your moneymanager datas",
        autocompletion=path_autocomplete(),
    ),
    config_filename: str = typer.Option(
        ".moneymanager",
        envvar="MONEYMANAGER_CONFIG_FILENAME",
        help="Name of your moneymanager config file, relative to the MoneyManager path.",
        autocompletion=path_autocomplete(),
    ),
    debug: bool = typer.Option(False, help="Show some debug values"),
):
    """
    Define root options, and initialize the cache.
    """
    paths = MoneymanagerPaths(moneymanager_path, config_filename)
    if ctx.invoked_subcommand != "init" and not paths.config.exists():
        console.print(
            "[bold red]ERROR :[/] you are not in a MoneyManager directory! "
            "Please either go to your MoneyManager directory, or set the [green]MONEYMANAGER_PATH[/] environ variable, "
            "or specify the MoneyManager path using [magenta]--moneymanager_path[/], "
            "or initialize MoneyManager here using [magenta]moneymanager init[/]\n\n"
            "Check the documentation for more informations: https://todo.com",
        )
        raise SystemExit(1)
    init_cache(paths, debug)


@app.command()
def init():
    init_paths()
    console.print(
        "All the missing files have been created! "
        "Install the defaults readers using [magenta]moneymanager reader install-defaults[/], and import your first file with [magenta]moneymanager import[/]!"
    )


@app.command()
@with_load_and_save
def categories(
    show_empty: Annotated[bool, typer.Option(help="Show categories with 0 transactions.")] = False,
    before: BeforeOption = None,
    after: AfterOption = None,
):
    """
    Shows a tree view of your expenses grouped by categories.
    """
    prompt_automatic_grouping(preview=True)
    _filter = filter_helper(before, after)
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
            value = sum(tr.amount for tr in _filter(group.all_transactions))
            number = len(list(_filter(group.all_transactions)))
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
@with_load_and_save
def transactions(
    before: BeforeOption = None,
    after: AfterOption = None,
):
    """
    Lists all your transactions.
    """
    prompt_automatic_grouping(preview=True)
    _filter = filter_helper(before, after)

    table = transactions_table(sorted(_filter(cache.transactions), key=lambda tr: tr.date))
    console.print(table)


@app.command()
@with_load
def accounts():
    """
    Shows a recap of your accounts state.
    """
    prompt_automatic_grouping(preview=True)
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


@app.command(name="import")
@with_load_and_save
def import_(
    path: Annotated[Path, typer.Argument(help="Path to the export(s).", autocompletion=path_autocomplete())],
    copy: Annotated[bool, typer.Option(help="Do a copy instead of moving the file.")] = False,
):
    """
    Import a bank export to your exports folder. This move the file.
    """
    if not path.exists():
        console.print("Please enter a valid path !")
        return

    new_transactions: set[Transaction] = set()
    file_paths: Iterable[Path] = path.glob("*") if path.is_dir() else (path,)

    new_transactions = set()
    for file_path in file_paths:
        if file_path.is_dir():
            continue
        res = import_transactions_export(file_path, copy)
        if res is not None:
            new_transactions.update(res)

    if new_transactions:
        infos = prompt_automatic_grouping(transactions=new_transactions)
        if infos.groups_updated == 0:
            console.print(
                Markdown(
                    f"Imported **{len(new_transactions)}** new transaction(s), but not groups matched the new entries."
                )
            )
            return
        plural = "different" if infos.groups_updated > 1 else "single"
        console.print(
            Markdown(
                f"Imported **{len(new_transactions)}** new transaction(s)!\n"
                f"Found **{infos.binds_added}** bind(s) to add, for **{infos.groups_updated}** {plural} group(s)."
            )
        )
    else:
        console.print("Not any new transaction found!")
