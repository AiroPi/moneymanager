from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, cast
from urllib import request

import typer
from pydantic_core import from_json

from moneymanager import (
    cache,
    filter_helper,
)
from moneymanager.autogroup import prompt_automatic_grouping
from moneymanager.loaders import (
    MoneymanagerPaths,
    get_reader,
    import_transactions_export,
    init_cache,
    init_paths,
    load_cache,
    save_data,
)
from moneymanager.ui import (
    Columns,
    Group as RichGroup,
    Markdown,
    Panel,
    Pretty,
    Table,
    Text,
    Tree,
    console,
    format_amount,
    transactions_table,
)
from moneymanager.utils import github_download

if TYPE_CHECKING:
    from moneymanager.group import AutoGroupRuleSets, Group
    from moneymanager.transaction import Transaction


GRAFANA_PATH = Path("./grafana")
GRAFANA_DATA_PATH = GRAFANA_PATH / "exports/"

app = typer.Typer(no_args_is_help=True)
debug_subcommands = typer.Typer(hidden=True, no_args_is_help=True)
app.add_typer(debug_subcommands, name="debug", help="Debug commands.")
reader_subcommands = typer.Typer(no_args_is_help=True, help="Commands related to readers.")
app.add_typer(reader_subcommands, name="reader")
manage_subcommands = typer.Typer(no_args_is_help=True, help="Commands to manage your groups, etc.")
app.add_typer(manage_subcommands, name="manage")
update_subcommands = typer.Typer(no_args_is_help=True, help="Commands to update the database.")
app.add_typer(update_subcommands, name="update")
grafana_subcommands = typer.Typer()
app.add_typer(grafana_subcommands, name="grafana")

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


@reader_subcommands.command(name="install-defaults")
def reader_install_defaults(
    path: Annotated[
        Path, typer.Argument(help="The directory to install the readers to.", autocompletion=path_autocomplete())
    ] = Path("./readers"),
):
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
        print(f"{file['name']} downloaded successfully.")

    print("Readers downloaded successfully.")


@reader_subcommands.command(name="instructions")
def reader_instructions(
    reader_path: Annotated[
        Path,
        typer.Argument(help="The reader you want instruction from.", autocompletion=path_autocomplete()),
    ],
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


@grafana_subcommands.command(name="help")
def grafana_help():
    console.print(
        Markdown(
            "Moneymanager made the choice of using **Grafana** to let you visualize your datas using graphs.\n"
            "This way, you can include your money datas into your own Grafana (if you have one), you can easily create "
            "your own graphs and visualize your data the way you want, and you can benefit from a very good "
            "and intuitive interface!\n\n"
            "Nevertheless, this needs you to launch a Grafana instance. The easiest way is using **Docker**.\n"
            "- Run the command `moneymanager grafana setup`\n"
            "- Install Docker if not present\n"
            "- Start Grafana using `docker compose up`\n"
            "- Go to [http://localhost:80](http://localhost:80)`\n"
            "- Login using `admin`/`admin`\n"
            "- Run the command `moneymanager grafana export` to re-export your datas if they changed\n"
            "Further instructions will come later..."
        )
    )


@grafana_subcommands.command(name="export")
@with_load
def grafana_export():
    from .exporter import grapfana_transactions_exporter

    console.print("Exporting data for grafana...")

    if not GRAFANA_DATA_PATH.exists():
        GRAFANA_DATA_PATH.mkdir(parents=True)

    grapfana_transactions_exporter(GRAFANA_DATA_PATH / "transactions.json")


@grafana_subcommands.command("setup")
@with_load
def grafana_setup():
    if not GRAFANA_PATH.exists():
        GRAFANA_PATH.mkdir()

    console.print("Downloading grafana related resources...")
    github_download(Path("grafana"), GRAFANA_PATH)

    console.print(f"Move {GRAFANA_PATH / 'compose.yaml'} to current directory.")
    (GRAFANA_PATH / "compose.yaml").rename(Path(".") / "compose.yaml")

    grafana_export()

    console.print(Markdown("Grafana setup ! Use `docker compose up` and go to [http://localhost:80](localhost:80)."))


@update_subcommands.command(name="auto-group")
@with_load_and_save
def update_auto_group():
    """
    Update auto group binds.
    """
    infos = prompt_automatic_grouping()
    if infos.groups_updated == 0:
        console.print("Not any group to update.")
        return
    plural = "different" if infos.groups_updated > 1 else "single"
    console.print(
        f"Found [bold]{infos.binds_added}[/bold] groups to add, [bold]{infos.binds_removed}[/bold] groups "
        f"to remove, for [bold]{infos.groups_updated}[/bold] {plural} [default not bold]group(s)."
    )


@manage_subcommands.command(name="groups")
@with_load
def manage_groups():
    """
    Invoke a TUI app to manage your groups (rename, delete, create...).

    Be careful, this command will rewrite your config files, and thus, remove all the commented sections, etc.
    """
    # Import is here to speedup the autocompletion, because textual takes ~0.1s to load.
    from moneymanager.textual_apps import ManageGroupsApp

    app = ManageGroupsApp()
    app.run()


if __name__ == "__main__":
    # typer.run(app)
    pass
