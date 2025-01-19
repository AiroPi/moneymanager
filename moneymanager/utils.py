from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib import request

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema, from_json


def fix_string(string: str):
    string = string.encode().decode("utf-8-sig")
    string = string.strip()
    return string


class ValuesIterDict[K, T](dict[K, T]):
    def __iter__(self):  # type: ignore
        yield from self.values()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.no_info_after_validator_function(cls, handler(dict))


def _github_download_file(url: str, destination: Path):
    with request.urlopen(url) as response, destination.open("wb+") as f:  # noqa: S310
        f.write(response.read())
    print(f"{destination} downloaded successfully.")


def _github_download_from_url(url: str, repo_path: Path, destination: Path):
    with request.urlopen(url) as response:  # noqa: S310
        contents = from_json(response.read())

    for content in contents:
        if content["type"] == "file":
            _github_download_file(content["download_url"], destination / Path(content["path"]).relative_to(repo_path))
        if content["type"] == "dir":
            (destination / Path(content["path"]).relative_to(repo_path)).mkdir(exist_ok=True)
            _github_download_from_url(content["url"], repo_path, destination)


def github_download(repo_path: Path, destination: Path):
    """
    Download a path from github, where repo_path is a relative path in the repo.
    This could be improved using multithreading or asyncio, but it is ok for our use case.
    """
    if not destination.exists():
        destination.mkdir(parents=True, exist_ok=True)

    if repo_path.is_absolute():
        repo_path = repo_path.relative_to("/")
    uri_path = repo_path.as_posix()

    url = f"https://api.github.com/repos/AiroPi/moneymanager/contents/{uri_path}?ref=master"
    _github_download_from_url(url, repo_path, destination)
