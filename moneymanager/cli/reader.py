from typing import Annotated
from urllib import request

import typer
from pydantic_core import from_json

from ..cache import cache
from ..loaders import get_reader, get_readers_from_file
from ..ui import Markdown, console

reader_subcommands = typer.Typer(no_args_is_help=True, help="Commands related to readers.")


def reader_autocomplete(args: list[str], ctx: typer.Context) -> list[str]:
    # TODO: https://github.com/fastapi/typer/discussions/1468
    return ["abc"]


@reader_subcommands.command(name="install-defaults")
def reader_install_defaults():
    """
    Installs the default readers available at https://github.com/AiroPi/moneymanager/tree/master/readers.
    """
    path = cache.paths.readers
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
    reader_name: Annotated[
        str, typer.Argument(help="The reader you want instructions from.", autocompletion=reader_autocomplete)
    ],
):
    """
    Gets the instructions to use a specific reader (how to make the transactions export).
    """
    reader_path = cache.paths.readers / f"{reader_name}.py"
    try:
        reader = get_reader(reader_path)
    except ValueError:
        console.print_exception()
        return
    if reader.__doc__ is None:
        console.print("No instructions found for this reader.")
        return
    console.print(Markdown(reader.__doc__))


@reader_subcommands.command(name="list")
def reader_list():
    """
    Get the list of available readers.
    """
    readers_fmt: list[str] = []

    for reader_path in cache.paths.readers.glob("*.py"):
        file_readers = get_readers_from_file(reader_path)
        if file_readers:
            file_readers_fmt = ", ".join(r.__name__ for r in file_readers)
            readers_fmt.append(f"[b]{reader_path.stem}[/b] : [i]{file_readers_fmt}[/i]")

    console.print(f"[u]Available readers :[/u]\n • {'\n • '.join(readers_fmt)}")
