import hashlib
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Protocol, TypeIs, cast

import yaml
from pydantic_core import from_json, to_json

from .cache import cache
from .group import GroupBinds, Groups
from .reader import ReaderABC, detect_reader
from .settings import AccountsSettings, AccountsSettingsValidator, AliasesT, InitialValuesT
from .transaction import Transaction, Transactions
from .ui import Markdown, console
from .utils import ValuesIterDict

DATA_PATH = Path("./data")
TRANSACTIONS_PATH = DATA_PATH / "transactions.json"
ALREADY_PARSED_PATH = DATA_PATH / "already_parsed_exports.json"
GROUP_BINDS = DATA_PATH / "group_binds.json"


@dataclass
class PathsOptions:
    readers: Path
    exports: Path
    rules: Path
    groups: Path
    account_settings: Path


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

    with cache.paths.groups.open(encoding="utf-8") as f:
        raw_groups: Any = yaml.safe_load(f) or []
    cache.groups = Groups.model_validate(raw_groups)


@loader()
def load_accounts_settings():
    """
    Loads "accounts_settings.yml".
    """
    with cache.paths.account_settings.open() as f:
        raw: Any = yaml.safe_load(f) or {}
    cache.accounts_settings = transform(AccountsSettingsValidator.model_validate(raw))


def transform(accounts_settings: AccountsSettingsValidator):
    """
    Used by load_accounts_settings_config. Will be deprecated soon. TODO.
    """
    aliases: AliasesT = {}
    for bank_entry in accounts_settings.aliases:
        bank_aliases = aliases.setdefault(bank_entry.bank, {})
        for account_alias in bank_entry.values:
            bank_aliases[account_alias.input] = account_alias.output

    initial_values: InitialValuesT = {}
    for bank_entry in accounts_settings.initial_values:
        bank_initial_values = initial_values.setdefault(bank_entry.bank, {})
        for initial_value in bank_entry.values:
            bank_initial_values[initial_value.account] = initial_value.value

    return AccountsSettings(aliases=aliases, initial_values=initial_values)


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
    if not paths.rules.exists():
        with paths.rules.open("w+") as f:
            f.write(
                "# This file contains the auto-groups rules. Check the documentation for details: https://github.com/AiroPi/moneymanager/master/readme.md#auto-grouping"
            )


# Data loaders (managed by the program) [.json files]


@loader()
def load_already_parsed() -> None:
    """
    Loads "data/already_parsed.json".
    """
    if not ALREADY_PARSED_PATH.exists():
        cache.already_parsed = []
        return

    with ALREADY_PARSED_PATH.open("rb") as f:
        cache.already_parsed = from_json(f.read())


@loader()
def load_transactions() -> None:
    """
    Loads "data/group_binds.json".
    """
    if not TRANSACTIONS_PATH.exists():
        cache.transactions = Transactions(set())
        return

    with TRANSACTIONS_PATH.open(encoding="utf-8") as f:
        cache.transactions = Transactions.model_validate_json(f.read())


@loader()
def load_group_binds() -> None:
    """
    Loads "data/group_binds.json".
    Groups needs to be already loaded in cache (from the config). (Call `load_groups_config()` first)
    Transactions needs to be already loaded in cache (from the data). (Call `load_transactions_data()` first)
    """
    if not GROUP_BINDS.exists():
        cache.group_binds = GroupBinds(set())
        return

    with GROUP_BINDS.open("rb") as f:
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
    if not DATA_PATH.exists():
        DATA_PATH.mkdir()

    with TRANSACTIONS_PATH.open("wb+") as f:
        f.write(to_json(cache.transactions, by_alias=True))
    with ALREADY_PARSED_PATH.open("wb+") as f:
        f.write(to_json(cache.already_parsed))
    with GROUP_BINDS.open("wb+") as f:
        f.write(to_json(cache.group_binds))


# Readers loader (interpreted files) [.py files]


@loader()
def load_readers():
    """
    Looks at all .py files in the given directory and get the Reader class from the `export()` function.
    """
    readers: list[type[ReaderABC]] = []

    for reader_path in (cache.paths.readers).glob("*.py"):
        try:
            module = get_reader(reader_path)
        except ValueError as e:
            print(e)
            continue

        try:
            export: Callable[[], Any] = getattr(module, "export")
        except AttributeError:
            print(f"{reader_path} does not contains an 'export' function.")
            continue

        exported = export()
        if not check_output_type(exported):
            raise TypeError(f"{reader_path}' export function does not return a list of readers.")

        readers.extend(exported)

    cache.readers = readers


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


def import_transactions_export(path: Path) -> set[Transaction] | None:
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

    count = 0
    new_transactions: set[Transaction] = set()
    with reader as content:
        for transaction in content:
            if transaction in cache.transactions:
                continue
            cache.transactions.add(transaction)
            new_transactions.add(transaction)
            count += 1

    new_name = cache.paths.exports / f"{fingerprint} - {path.name}"
    if path.name.startswith(fingerprint):
        new_name = cache.paths.exports / path.name

    path.rename(new_name)
    cache.already_parsed.append(fingerprint)
    console.print(Markdown(f"Successfully imported the file `{path}` with **{count}** new transactions !"))
    return new_transactions


# Others


def init_cache(paths: PathsOptions, debug_mode: bool = False):
    """
    Init the cache with default values and values from the environ variables / command arguments.
    """
    cache.paths = paths
    cache.debug_mode = debug_mode
    cache.banks = ValuesIterDict()  # dynamically built


def load_cache(force_load: bool = False):
    """
    Will load the config and the data in the cache.
    """
    load_readers(force_load)
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
    init_config()
    cache.paths.readers.mkdir(exist_ok=True)
    cache.paths.exports.mkdir(exist_ok=True)
    DATA_PATH.mkdir(exist_ok=True)
