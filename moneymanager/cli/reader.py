from pathlib import Path
from typing import Annotated
from urllib import request

import typer
from pydantic_core import from_json

from ..loaders import get_reader
from ..ui import Markdown, console
from .cli_utils import path_autocomplete

reader_subcommands = typer.Typer(no_args_is_help=True, help="Commands related to readers.")


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

    # TODO: use github_download
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
