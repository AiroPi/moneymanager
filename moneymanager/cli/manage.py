import typer

from .cli_utils import with_load

manage_subcommands = typer.Typer(no_args_is_help=True, help="Commands to manage your groups, etc.")


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
