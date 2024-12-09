from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from pydantic_core import from_json, to_json
from rich.columns import Columns
from rich.console import Console, Group as RichGroup
from rich.markdown import Markdown
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
from moneymanager.transaction import Transactions, load_transactions
from moneymanager.utils import ValuesIterDict, format_amount

if TYPE_CHECKING:
    from moneymanager.group import AutoGroupRuleSets, Group
    from moneymanager.reader import ReaderABC
    from moneymanager.transaction import Transaction


DATA_PATH = Path("./data")
TRANSACTIONS_PATH = DATA_PATH / "transactions.json"
ALREADY_PARSED_PATH = DATA_PATH / "already_parsed_exports.json"

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
):
    paths_options = PathsOptions(readers, exports, rules, groups, settings)
    load_cache(paths_options)
    parse_transactions(paths_options)


def load_cache(paths: PathsOptions):
    cache.banks = ValuesIterDict()
    cache.groups = load_groups(paths.groups)
    cache.grouping_rules = load_grouping_rules(paths.rules)
    cache.accounts_settings = load_accounts_settings(paths.account_settings)

    cache.transactions = load_transactions(TRANSACTIONS_PATH)
    cache.already_parsed = []


def parse_transactions(paths: PathsOptions):
    readers: list[type[ReaderABC]] = load_readers(paths.readers)

    if ALREADY_PARSED_PATH.exists():
        with ALREADY_PARSED_PATH.open("rb") as f:
            cache.already_parsed = from_json(f.read())

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

    bind_table: dict[int, AutoGroupRuleSets] = {}
    new_matches: dict[int, set[Transaction]] = {}
    for transaction in cache.transactions:
        for grouping_rule in cache.grouping_rules:
            if grouping_rule.group in transaction.groups:
                continue
            if grouping_rule.test_match(transaction):
                bind_table.setdefault(id(grouping_rule), grouping_rule)
                new_matches.setdefault(id(grouping_rule), set()).add(transaction)

    prompt_confirmation(bind_table, new_matches)

    with TRANSACTIONS_PATH.open("w") as f:
        f.write(Transactions(cache.transactions).model_dump_json(indent=4, by_alias=True))
    with ALREADY_PARSED_PATH.open("wb") as f:
        f.write(to_json(cache.already_parsed))


def prompt_confirmation(bind_table: dict[int, AutoGroupRuleSets], new_matches: dict[int, set[Transaction]]):
    if new_matches:
        console.print("Auto groups matched new transactions !")
    for id_, transactions in new_matches.items():
        auto_group_ruleset = bind_table[id_]
        console.print("The following rule matched the following transactions")
        console.print(auto_group_ruleset.rules)

        table = transactions_table(transactions)

        console.print(table)
        confirmed = Confirm.ask(f"Assign the group {auto_group_ruleset.group.name} ?")
        if confirmed:
            for tr in transactions:
                tr.bind_group(auto_group_ruleset.group)

        console.clear()


@app.command()
def categories(
    before: datetime | None = typer.Option(None),
    after: datetime | None = typer.Option(None),
):
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
            bold = "[b]" if group.subgroups else ""
            leaf = tree.add(f"{bold}{group.name}")

            value = sum(tr.amount for tr in filter(group.transactions.all()))
            table.add_row(format_amount(value), str(len(list(filter(group.transactions.all())))))
            if group.subgroups:
                build_tree_table(group.subgroups, leaf, table)
        return table, tree

    table, tree = build_tree_table(cache.groups)

    console.print(Columns([table, RichGroup("[bold]groups", *tree.children)]))


@app.command()
def accounts(ctx: typer.Context):
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
    before: datetime | None = typer.Option(None),
    after: datetime | None = typer.Option(None),
):
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


if __name__ == "__main__":
    typer.run(app)
