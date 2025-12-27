from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
from collections.abc import Callable, Iterable
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeIs, cast

import yaml
from pydantic_core import from_json, to_json

from .cache import cache
from .config import MoneymanagerConfig
from .errors import MissingConfigFile
from .group import GroupBinds, Groups
from .reader import ReaderABC, detect_reader
from .settings import AccountsSettings
from .transaction import Transaction, Transactions
from .ui import Markdown, console
from .utils import ValuesIterDict

# Paths loaders


def path_property(type: Literal["dir", "file"]):
    def inner(f: Callable[[MoneymanagerPaths], Path]) -> Path:
        def resolver(self: MoneymanagerPaths):
            if self.is_resolved is False:
                raise ValueError("MoneymanagerPaths is not resolved yet.")
            return self.moneymanager_path / getattr(self, f"{f.__name__}_{type}name")

        return property(resolver)  # type: ignore

    return inner


class MoneymanagerPaths:
    """
    Store all the paths used by MoneyManager. Must be configurable using environ variable or the config file.
    """

    def __init__(self, path: Path | None, config_filename: str | None, init_command: bool = False):
        self._init_command = init_command
        self._resolved = False
        self._moneymanager_path: Path | None = path
        self._config_filename: str | None = config_filename
        self._config_resolved_path: Path | None = None

        self.resolve_paths()

    def resolve_paths(self):
        if self._moneymanager_path is None:
            self.resolve_moneymanager_path()

        self.resolve_config_path()

        config = load_core_config(self.config)
        self.resolve_general_paths(config)

        self._resolved = True

    def resolve_moneymanager_path(self):
        """
        This function will set the base path according to the following rules:
        - if the `--path` option is set, it takes the precedence over all other parameters
        - otherwise, if `MONEYMANAGER_PATH` environ variable is not defined, it defaults to the current working
        directory
        - otherwise, if `MONEYMANAGER_PATH` environ variable is set, but there is a moneymanager config file in the
        current working directory, then the current working directory is used.
        - otherwise, the `MONEYMANAGER_PATH` environ variable path is used as path.
        """
        if not (env := os.getenv("MONEYMANAGER_PATH")):
            self._moneymanager_path = Path(".")
        else:
            try:
                self.discover_config(Path("."))
            except MissingConfigFile:
                self._moneymanager_path = Path(env)
            else:
                self._moneymanager_path = Path(".")

    def resolve_config_path(self):
        if TYPE_CHECKING:
            assert isinstance(self._moneymanager_path, Path)

        try:
            self._config_path = self.discover_config(self._moneymanager_path)
        except MissingConfigFile:
            if not self._init_command:
                raise
            self._config_path = self._moneymanager_path / ".moneymanager"

    def discover_config(self, path: Path) -> Path:
        """
        Look for a config file in the given path. The rules used to discover the config file are:
        - if `--config` option is set, it will check for a {path}/{config} file and fail if not present (nb: `--config`
        option will also be set if the env variable `MONEYMANAGER_CONFIG_FILENAME` is defined.)
        - otherwise, it will looks for files in the following order:
            - `.moneymanager`
            - `.moneymanager.yml`
            - `.moneymanager.yaml`
            - `moneymanager.yml`
            - `moneymanager.yaml`
        - if none of the previous file is found, this raises a MissingConfigFile error.
        """

        def find_existing(files: Iterable[Path]) -> Path | None:
            return next(filter(os.path.exists, files), None)

        if self._config_filename is not None:
            filenames = (path / self._config_filename,)
        else:
            filenames = tuple(
                path / fn
                for fn in (
                    ".moneymanager",
                    ".moneymanager.yaml",
                    ".moneymanager.yml",
                    "moneymanager.yaml",
                    "moneymanager.yml",
                )
            )

        if not (res := find_existing(filenames)):
            raise MissingConfigFile(filenames)
        return res

    def resolve_general_paths(self, config: MoneymanagerConfig):
        self.data_dirname: str = config.data_dirname or os.getenv("MONEYMANAGER_DATA_DIRNAME") or "data"
        self.readers_dirname: str = config.readers_dirname or os.getenv("MONEYMANAGER_READERS_DIRNAME") or "readers"
        self.exports_dirname: str = config.exports_dirname or os.getenv("MONEYMANAGER_EXPORTS_DIRNAME") or "exports"
        self.grafana_dirname: str = "grafana"
        self.groups_filename: str = config.groups_filename or os.getenv("MONEYMANAGER_GROUPS_FILENAME") or "groups.yml"
        self.account_settings_filename: str = (
            config.account_settings_filename
            or os.getenv("MONEYMANAGER_ACCOUNT_SETTINGS_FILENAME")
            or "accounts_settings.yml"
        )

        if config.grafana_dirname or os.getenv("MONEYMANAGER_GRAFANA_DIRNAME"):
            # TODO: grafana dirname can't be changed for now.
            console.print("[yellow]WARNING:[/] grafana directory name can't be changed for now. Setting is ignored.")

    @property
    def is_resolved(self):
        return self._resolved

    @property
    def moneymanager_path(self) -> Path:
        if self._moneymanager_path is None:
            raise ValueError("The function MoneymanagerPaths.resolve_paths should be called first.")
        return self._moneymanager_path

    @property
    def config(self) -> Path:
        return self._config_path

    @path_property("dir")
    def readers(self) -> Path: ...

    @path_property("dir")
    def exports(self) -> Path: ...

    @path_property("file")
    def groups(self) -> Path: ...

    @path_property("file")
    def account_settings(self) -> Path: ...

    @path_property("dir")
    def grafana(self) -> Path: ...

    @path_property("dir")
    def data(self) -> Path: ...

    @property
    def grafana_exports(self) -> Path:
        return self.grafana / "exports"

    @property
    def transactions(self) -> Path:
        return self.data / "transactions.json"

    @property
    def already_parsed(self) -> Path:
        return self.data / "already_parsed_exports.json"

    @property
    def group_binds(self) -> Path:
        return self.data / "group_binds.json"


type LoaderFIn = Callable[[], None]


class LoaderFOut(Protocol):
    def __call__(self, force_load: bool = False): ...


def loader(cache_attr: str | None = None) -> Callable[[LoaderFIn], LoaderFOut]:
    def inner(f: LoaderFIn) -> LoaderFOut:
        _cache_attr = cache_attr or f.__name__.removeprefix("load_")

        @wraps(f)
        def wrapped(force_load: bool = False):
            if not force_load and cache.is_loaded(_cache_attr):
                return
            f()

        return wrapped

    return inner


# Config loaders (managed by the program and the user) [.yml files]


@loader()
def load_groups():
    """
    Loads "groups.yml".
    """
    raw = yaml_load(cache.paths.groups, [])
    cache.groups = Groups.model_validate(raw)


@loader()
def load_accounts_settings():
    """
    Loads "accounts_settings.yml".
    """
    raw = yaml_load(cache.paths.account_settings, [])
    cache.accounts_settings = AccountsSettings.model_validate(raw)


def load_config(force_load: bool = False):
    load_groups(force_load)
    load_accounts_settings(force_load)


def save_config():
    with cache.paths.groups.open("wb+") as f:
        f.write(
            yaml.safe_dump(
                cache.groups.model_dump(exclude_defaults=True, by_alias=True),
                encoding="utf8",
                allow_unicode=True,
                width=120,
                sort_keys=False,
            )
        )


def init_config():
    """
    Function to create empty config files.
    """
    paths = cache.paths
    if not paths.account_settings.exists():
        with paths.account_settings.open("w+") as f:
            f.write(
                "# This file contains some accounts settings. Check the documentation for details: https://github.com/AiroPi/moneymanager/master/readme.md#accounts-settings"
            )
    if not paths.groups.exists():
        with paths.groups.open("w+") as f:
            f.write(
                "# This file contains all the groups. Check the documentation for details: https://github.com/AiroPi/moneymanager/master/readme.md#groups"
            )


# Data loaders (managed by the program) [.json files]


@loader()
def load_already_parsed() -> None:
    """
    Loads "data/already_parsed.json".
    """
    if not cache.paths.already_parsed.exists():
        cache.already_parsed = []
        return

    with cache.paths.already_parsed.open("rb") as f:
        cache.already_parsed = from_json(f.read())


@loader()
def load_transactions() -> None:
    """
    Loads "data/group_binds.json".
    """
    if not cache.paths.transactions.exists():
        cache.transactions = Transactions(set())
        return

    with cache.paths.transactions.open(encoding="utf-8") as f:
        cache.transactions = Transactions.model_validate_json(f.read())


@loader()
def load_group_binds() -> None:
    """
    Loads "data/group_binds.json".
    Groups needs to be already loaded in cache (from the config). (Call `load_groups_config()` first)
    Transactions needs to be already loaded in cache (from the data). (Call `load_transactions_data()` first)
    """
    if not cache.paths.group_binds.exists():
        cache.group_binds = GroupBinds(set())
        return

    with cache.paths.group_binds.open("rb") as f:
        cache.group_binds = GroupBinds.model_validate_json(f.read())


def load_data(force_load: bool = False):
    """
    Loads the datas from previously saved files and add them to the cache.
    `load_config(...)` needs to be called first.
    """
    load_already_parsed(force_load)
    load_transactions(force_load)
    load_group_binds(force_load)


def save_data():
    """
    Save the datas from the cache into json files.
    """
    if cache.dry_run:
        return

    if not cache.paths.data.exists():
        cache.paths.data.mkdir()

    with cache.paths.transactions.open("wb+") as f:
        f.write(to_json(cache.transactions, by_alias=True))
    with cache.paths.already_parsed.open("wb+") as f:
        f.write(to_json(cache.already_parsed))
    with cache.paths.group_binds.open("wb+") as f:
        f.write(to_json(cache.group_binds))


# Readers loader (interpreted files) [.py files]


@loader()
def load_readers():
    """
    Looks at all .py files in the given directory and get the Reader class from the `export()` function.
    """
    readers: list[type[ReaderABC]] = []

    for reader_path in cache.paths.readers.glob("*.py"):
        file_readers = get_readers_from_file(reader_path)
        if file_readers:
            readers.extend(file_readers)

    cache.readers = readers


def get_readers_from_file(reader_path: Path) -> list[type[ReaderABC]] | None:
    try:
        module = get_reader(reader_path)
    except ValueError as e:
        console.print(e, style="bold red")
        return

    try:
        export: Callable[[], Any] = getattr(module, "export")
    except AttributeError:
        console.print(f"{reader_path} does not contains an 'export' function.", style="bold red")
        return

    exported = export()
    if not check_output_type(exported):
        console.print(f"{reader_path}' export function does not return a list of readers.", style="bold red")
        return

    return exported


def get_reader(path: Path):
    """
    Imports the given path as a python module.
    The code is evaluated! Be careful.
    """
    spec = importlib.util.spec_from_file_location(str(path), str(path))
    if not spec:
        raise ValueError(f"The file {path} cannot be imported.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore

    return module


def check_output_type(output: Any) -> TypeIs[list[type[ReaderABC]]]:
    """
    Asserts that the type returned by the `export()` function from the reader module is right.
    """
    if not isinstance(output, list):
        return False
    output = cast(list[Any], output)
    return all(issubclass(reader_cls, ReaderABC) for reader_cls in output)


# Exports reader (read files dropped in the 'exports' folder) [any (most likely csv files)]


def import_transactions_export(path: Path, copy: bool = False, update: bool = False) -> set[Transaction] | None:
    file = path.open("rb")
    fingerprint = hashlib.md5(file.read()).hexdigest()  # noqa: S324
    if fingerprint in cache.already_parsed:
        console.print(Markdown(f"The file `{path}` seems to be already imported !"))
        return
    file.seek(0)

    reader = detect_reader(file)
    if reader is None:
        file.close()
        console.print(
            Markdown(
                f"Didn't found any reader that match the file `{path}`. Can't be imported. Maybe you need to install the defaults ones with `moneymanager "
                "reader install-defaults`.\n"
                "Otherwise, consider creating your own."
            )
        )
        return

    new_transactions: set[Transaction] = set()
    updated_transaction = 0
    with reader as content:
        for transaction in content:
            if transaction in cache.transactions:
                if update:
                    existing = cache.transactions[transaction.id]
                    if existing.label != transaction.label:
                        existing.label = transaction.label
                        updated_transaction += 1
                continue
            cache.transactions.add(transaction)
            new_transactions.add(transaction)

    new_name = cache.paths.exports / f"{fingerprint} - {path.name}"
    if path.name.startswith(fingerprint):
        new_name = cache.paths.exports / path.name

    if not cache.dry_run:
        if copy:
            shutil.copy(path, new_name)
        else:
            path.rename(new_name)
    cache.already_parsed.append(fingerprint)
    console.print(
        Markdown(f"Successfully imported the file `{path}` with **{len(new_transactions)}** new transactions !")
    )
    if update:
        console.print(Markdown(f"**{updated_transaction}** transactions updated !"))
    return new_transactions


# Others


def init_cache(paths: MoneymanagerPaths, debug_mode: bool = False, dry_run: bool = False):
    """
    Init the cache with default values and values from the environ variables / command arguments.
    """
    cache.paths = paths
    cache.debug_mode = debug_mode
    cache.dry_run = dry_run
    cache.banks = ValuesIterDict()  # dynamically built


def load_cache(force_load: bool = False):
    """
    Will load the config and the data in the cache.
    """
    load_config(force_load)
    load_data(force_load)

    # if cache.debug_mode:
    #     console.print(Markdown("# Banks"))
    #     console.print(cache.banks)
    #     console.print(Markdown("# Groups"))
    #     console.print(cache.groups)
    #     console.print(Markdown("# Grouping rules"))
    #     console.print(cache.grouping_rules)
    #     console.print(Markdown("# Accounts settings"))
    #     console.print(cache.accounts_settings)
    #     if Confirm.ask("Continue?"):
    #         console.clear()
    #     else:
    #         raise SystemExit(0)


def init_paths():
    """
    Creates empty files and directories used by the app.
    """
    if not cache.paths.moneymanager_path.exists():
        console.print(
            f"[red]ERROR:[/] the directory {cache.paths.moneymanager_path} doesn't exist. Please create it before going"
            " further."
        )
        raise SystemExit(1)
    init_config()
    cache.paths.config.touch(exist_ok=True)
    cache.paths.readers.mkdir(exist_ok=True)
    cache.paths.exports.mkdir(exist_ok=True)
    cache.paths.data.mkdir(exist_ok=True)


def load_core_config(path: Path):
    """
    Read the moneymanager config file.
    """
    raw = yaml_load(path, {})
    return MoneymanagerConfig.model_validate(raw)


def yaml_load[T](path: Path, default: T) -> T:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or default
    return default
