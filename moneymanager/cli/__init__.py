from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from trogon.typer import init_tui

from moneymanager.errors import MissingConfigFile

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
from .cli_utils import (
    AfterOption,
    BeforeOption,
    FirstOption,
    LastOption,
    path_autocomplete,
    with_load,
    with_load_and_save,
)
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
init_tui(app)


@app.callback()
def common(
    ctx: typer.Context,
    moneymanager_path: Path | None = typer.Option(
        None,
        "--path",
        "-p",
        help="Location of your moneymanager datas.",
        autocompletion=path_autocomplete(),
        show_default=False,
    ),
    config_filename: str | None = typer.Option(
        None,
        "--config",
        "-c",
        envvar="MONEYMANAGER_CONFIG_FILENAME",
        help="Name of your moneymanager config file, relative to the MoneyManager path.",
        autocompletion=path_autocomplete(),
        show_default=False,
        show_envvar=False,
    ),
    debug: bool = typer.Option(False, help="Show some debug values"),
    dry_run: bool = typer.Option(False, help="Do not write data to disk"),
):
    """
    Define root options, and initialize the cache.
    """
    if ctx.invoked_subcommand == "init":
        paths = MoneymanagerPaths(moneymanager_path, config_filename, init_command=True)
    else:
        try:
            paths = MoneymanagerPaths(moneymanager_path, config_filename)
        except MissingConfigFile as e:
            console.print(
                "[bold red]ERROR :[/] you are not in a MoneyManager directory! "
                "Please either go to your MoneyManager directory, or set the [green]MONEYMANAGER_PATH[/] environ variable, "
                "or specify the MoneyManager path using [magenta]--path[/], "
                "or initialize MoneyManager here using [magenta]moneymanager init[/]\n\n"
                "Check the documentation for more informations: https://todo.com\n\n",
                f"Missing file: [blue]{'[/] or [blue]'.join(map(str, e.paths))}[/]",
            )
            raise SystemExit(1)
    init_cache(paths, debug, dry_run)


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
    _filter = filter_helper(before=before, after=after)
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
    first: FirstOption = None,
    last: LastOption = None,
    show_id: Annotated[bool, typer.Option(help="Show bank & account ID instead of display name.")] = False,
    account: Annotated[list[str] | None, typer.Option(help="Filter the account to show")] = None,
):
    """
    Lists all your transactions.
    """
    prompt_automatic_grouping(preview=True)
    if first is not None and last is not None:
        console.print("--first and --last options are incompatibles")
        return
    _filter = filter_helper(
        before=before,
        after=after,
        first=first,
        last=last,
        accounts=account,
    )

    table = transactions_table(_filter(cache.transactions), show_id)
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
            value += account.initial_balance

            total += value

            _real_bank_name = f" [i]({bank.name})[/i]" if bank.display_name != bank.name else ""
            _real_account_name = f" [i]({account.name})[/i]" if account.display_name != account.name else ""
            accounts_table.add_row(
                f"{bank.display_name}{_real_bank_name}",
                f"{account.display_name}{_real_account_name}",
                f"{value:,.2f}€",
            )

    accounts_table.columns[2].footer = f"[u]{total:,.2f}€"

    console.print(accounts_table)


@app.command(name="import")
@with_load_and_save
def import_(
    path: Annotated[Path, typer.Argument(help="Path to the export(s).", autocompletion=path_autocomplete())],
    copy: Annotated[bool, typer.Option(help="Do a copy instead of moving the file.")] = False,
    update: Annotated[bool, typer.Option(help="Update transaction label when supported.")] = False,
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
        res = import_transactions_export(file_path, copy, update)
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


@app.command()
@with_load_and_save
def migrate_credit_mutuel(
    convert_account: Annotated[list[str], typer.Option(help="from:to convert account name")],
    convert_bank: Annotated[str, typer.Option(help="from:to convert bank name")],
    delete_after: Annotated[datetime, typer.Option(help="delete transactions after dd-mm-yyyy (included)")],
) -> None:
    old_bank, new_bank = convert_bank.split(":")
    _convert_acc = {acc.split(":")[0]: acc.split(":")[1] for acc in convert_account}

    to_delete = set["Transaction"]()
    updated = 0
    for tr in cache.transactions:
        if tr.bank.name == old_bank:
            if tr.date >= delete_after.date():
                to_delete.add(tr)
                continue
            tr.account_name = _convert_acc[tr.account_name]
            tr.bank_name = new_bank
            updated += 1
    cache.transactions.root.difference_update(to_delete)

    console.print(f"Removed {len(to_delete)} transactions and updated {updated}")


@app.command()
def clean_bind_groups():
    from json import dump, load
    from typing import Any

    from ..loaders import load_transactions

    load_transactions()
    transaction_ids = {tr.id for tr in cache.transactions}

    with cache.paths.group_binds.open(encoding="utf-8") as f:
        group_binds: list[Any] = load(f)

    to_remove = list[int]()
    for i, bind in enumerate(group_binds):
        if bind["transaction_id"] not in transaction_ids:
            to_remove.append(i)
    for i in to_remove[::-1]:
        group_binds.pop(i)

    console.print(f"Removed {len(to_remove)} non-existant transaction from groups.")

    with cache.paths.group_binds.open("w", encoding="utf-8") as f:
        dump(group_binds, f)
