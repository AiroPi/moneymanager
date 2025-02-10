import typer

from moneymanager.autogroup import prompt_automatic_grouping
from moneymanager.ui import console

from .cli_utils import with_load_and_save

update_subcommands = typer.Typer(no_args_is_help=True, help="Commands to update the database.")


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
