from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Annotated
from urllib import request

import typer
from pydantic_core import from_json, to_json
from rich.columns import Columns
from rich.console import Console, Group as RichGroup
from rich.markdown import Markdown
from rich.panel import Panel
from rich.pretty import Pretty
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from moneymanager import (
    cache,
    detect_reader,
    filter_helper,
    load_accounts_settings,
    load_grouping_rules,
    load_groups,
    load_readers,
)
from moneymanager.group import GroupBind, load_binds
from moneymanager.reader import get_reader
from moneymanager.transaction import load_transactions
from moneymanager.utils import ValuesIterDict, format_amount

if TYPE_CHECKING:
    from moneymanager.group import AutoGroupRuleSets, Group
    from moneymanager.reader import ReaderABC
    from moneymanager.transaction import Transaction


DATA_PATH = Path("./data")
TRANSACTIONS_PATH = DATA_PATH / "transactions.json"
ALREADY_PARSED_PATH = DATA_PATH / "already_parsed_exports.json"
GROUP_BINDS = DATA_PATH / "group_binds.json"

app = typer.Typer()
console = Console()


@dataclass
class PathsOptions:
    readers: Path
    exports: Path
    rules: Path
    groups: Path
    account_settings: Path


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


def load(paths: PathsOptions):
    load_cache(paths)
    parse_transactions(paths)
    do_auto_grouping()
    save_data()


def load_cache(paths: PathsOptions):
    cache.banks = ValuesIterDict()
    cache.groups = load_groups(paths.groups)
    cache.grouping_rules = load_grouping_rules(paths.rules)
    cache.accounts_settings = load_accounts_settings(paths.account_settings)

    cache.transactions = load_transactions(TRANSACTIONS_PATH)
    cache.already_parsed = load_already_parsed(ALREADY_PARSED_PATH)
    cache.group_binds = load_binds(GROUP_BINDS)

    if cache.debug_mode:
        console.print(Markdown("# Banks"))
        console.print(cache.banks)
        console.print(Markdown("# Groups"))
        console.print(cache.groups)
        console.print(Markdown("# Grouping rules"))
        console.print(cache.grouping_rules)
        console.print(Markdown("# Accounts settings"))
        console.print(cache.accounts_settings)
        if Confirm.ask("Continue?"):
            console.clear()
        else:
            raise SystemExit(0)


def load_already_parsed(path: Path) -> list[str]:
    if path.exists():
        with path.open("rb") as f:
            return from_json(f.read())
    else:
        return []


def parse_transactions(paths: PathsOptions):
    readers: list[type[ReaderABC]] = load_readers(paths.readers)

    for export_path in Path(paths.exports).glob("*"):
        if str(export_path.absolute()) in cache.already_parsed:
            continue

        file = export_path.open("rb")
        reader = detect_reader(readers, file)
        if not reader:
            file.close()
            print(f"No reader available for the export {export_path}")
            continue

        count = 0
        with reader as content:
            for transaction in content:
                if transaction in cache.transactions:
                    continue
                cache.transactions.add(transaction)
                count += 1

        if count:
            console.print(f"Loaded [bold]{count}[/bold] new transactions from {export_path.absolute()}.")

        cache.already_parsed.append(str(export_path.absolute()))


def do_auto_grouping():
    for grouping_rule in cache.grouping_rules:
        matches: set[GroupBind] = set()
        for transaction in cache.transactions:
            if grouping_rule.test_match(transaction):
                matches.add(GroupBind.from_objects(transaction, grouping_rule.group, "auto"))
        prompt_confirmation(grouping_rule, matches)



def prompt_confirmation(grouping_rule: AutoGroupRuleSets, matches: set[GroupBind]):
    already_added = {bind for bind in grouping_rule.group.binds if bind.type == "auto"}
    removed = already_added - matches
    added = matches - already_added

    if not (removed or added):
        return

    console.print(
        f"[bold]:warning: Auto grouping detected some changes for the group [underline]{grouping_rule.group.name}!"
    )

    if removed:
        table = transactions_table(bind.transaction for bind in removed)
        console.print("The following elements will be unassigned:")
        console.print(table)
    if added:
        table = transactions_table(bind.transaction for bind in added)
        console.print("The following elements will be assigned:")
        console.print(table)

    if Confirm.ask("Confirm ?"):
        for bind in added:
            cache.group_binds.add(bind)
        for bind in removed:
            cache.group_binds.remove(bind)


def save_data():
    if not DATA_PATH.exists():
        DATA_PATH.mkdir()

    with TRANSACTIONS_PATH.open("wb+") as f:
        f.write(to_json(cache.transactions, by_alias=True))
    with ALREADY_PARSED_PATH.open("wb+") as f:
        f.write(to_json(cache.already_parsed))
    with GROUP_BINDS.open("wb+") as f:
        f.write(to_json(cache.group_binds))


@app.command()
def categories(
    ctx: typer.Context,
    show_empty: bool = typer.Option(False, help="Show categories with 0 transactions."),
    before: datetime | None = typer.Option(None),
    after: datetime | None = typer.Option(None),
):
    load(ctx.obj.paths)
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
def accounts(ctx: typer.Context):
    load(ctx.obj.paths)

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


@app.command()
def transactions(
    ctx: typer.Context,
    before: datetime | None = typer.Option(None),
    after: datetime | None = typer.Option(None),
):
    load(ctx.obj.paths)
    filter = filter_helper(before, after)

    table = transactions_table(sorted(filter(cache.transactions), key=lambda tr: tr.date))
    console.print(table)


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


@app.command()
def install_default_readers(path: Path = Path("./readers")):
    if not path.exists():
        path.mkdir()

    with request.urlopen("https://api.github.com/repos/AiroPi/moneymanager/contents/readers?ref=master") as response:
        files = from_json(response.read())

    for file in files:
        with request.urlopen(file["download_url"]) as response, (path / file["name"]).open("wb+") as f:  # noqa: S310
            f.write(response.read())
        print(f"{file["name"]} downloaded successfully.")

    print("Readers downloaded successfully.")


@app.command()
def reader_instructions(
    reader_path: Annotated[Path, typer.Argument(help="The reader you want instruction from.")],
):
    try:
        reader = get_reader(reader_path)
    except ValueError:
        console.print_exception()
        return
    if reader.__doc__ is None:
        console.print("No instructions found for this reader.")
        return
    console.print(Markdown(reader.__doc__))


@app.command(hidden=True)
def debug_auto_group(ctx: typer.Context, transaction_id: str):
    load(ctx.obj.paths)
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
def auto_group(ctx: typer.Context):
    load(ctx.obj.paths)


if __name__ == "__main__":
    typer.run(app)
