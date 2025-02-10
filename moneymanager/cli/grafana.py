from __future__ import annotations

from pathlib import Path

import typer

from ..cache import cache
from ..cli.cli_utils import with_load
from ..ui import (
    Markdown,
    console,
)
from ..utils import github_download

grafana_subcommands = typer.Typer()


@grafana_subcommands.command(name="help")
def grafana_help():
    console.print(
        Markdown(
            "MoneyManager made the choice of using **Grafana** to let you visualize your datas using graphs.\n"
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
    from moneymanager.exporter import grafana_transactions_exporter

    console.print("Exporting data for grafana...")

    if not cache.paths.grafana_exports.exists():
        cache.paths.grafana_exports.mkdir(parents=True)

    grafana_transactions_exporter(cache.paths.grafana_exports / "transactions.json")


@grafana_subcommands.command("setup")
@with_load
def grafana_setup():
    """
    Setup grafana to use it with MoneyManager and see your datas.
    """
    if not cache.paths.grafana.exists():
        cache.paths.grafana.mkdir()

    console.print("Downloading grafana related resources...")
    github_download(Path("grafana"), cache.paths.grafana)

    console.print(f"Move {cache.paths.grafana / 'compose.yaml'} to current directory.")
    (cache.paths.grafana / "compose.yaml").rename(cache.paths.moneymanager_path / "compose.yaml")

    grafana_export()

    console.print(
        "Grafana setup! "
        "Please go into your MoneyManager directory and use the command "
        "[magenta]docker compose up[/] and go to [link=http://localhost:80]http://localhost:80[/]."
    )
