import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeIs, cast

import yaml
from pydantic_core import from_json, to_json

from .cache import cache
from .group import GroupBinds, GroupingRules, Groups
from .reader import ReaderABC, detect_reader
from .settings import AccountsSettings, AccountsSettingsValidator, AliasesT, InitialValuesT
from .transaction import Transactions
from .ui import Confirm, Markdown, console
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


# Config loaders (managed by the program and the user) [.yml files]


def load_groups_config(path: Path) -> Groups:
    """
    Loads "groups.yml".
    """
    with path.open(encoding="utf-8") as f:
        raw_groups = yaml.safe_load(f)
    return Groups.model_validate(raw_groups)


def load_grouping_rules_config(path: Path) -> GroupingRules:
    """
    Loads "auto_group.yml"
    """
    with path.open(encoding="utf-8") as f:
        grouping_rule_definitions = yaml.safe_load(f)

    return GroupingRules.model_validate(grouping_rule_definitions)


def load_accounts_settings_config(path: Path) -> AccountsSettings:
    """
    Loads "accounts_settings.yml".
    """
    with path.open() as f:
        raw = yaml.safe_load(f)
    return transform(AccountsSettingsValidator.model_validate(raw))


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


def load_config():
    cache.groups = load_groups_config(cache.paths.groups)
    cache.grouping_rules = load_grouping_rules_config(cache.paths.rules)
    cache.accounts_settings = load_accounts_settings_config(cache.paths.account_settings)


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
    with cache.paths.rules.open("wb+") as f:
        result = cache.grouping_rules.model_dump(exclude_defaults=True, by_alias=True)

        f.write(
            yaml.safe_dump(
                result,
                encoding="utf8",
                allow_unicode=True,
                width=120,
                sort_keys=False,
            )
        )


# Data loaders (managed by the program) [.json files]


def load_already_parsed(path: Path) -> list[str]:
    """
    Loads "data/already_parsed.json".
    """
    if path.exists():
        with path.open("rb") as f:
            return from_json(f.read())
    else:
        return []


def load_transactions_data(path: Path) -> Transactions:
    """
    Loads "data/group_binds.json".
    """
    if not path.exists():
        return Transactions(set())

    with path.open(encoding="utf-8") as f:
        transactions = Transactions.model_validate_json(f.read())

    return transactions


def load_binds_data(path: Path) -> GroupBinds:
    """
    Loads "data/group_binds.json".
    Groups needs to be already loaded in cache (from the config). (Call `load_groups_config()` first)
    Transactions needs to be already loaded in cache (from the data). (Call `load_transactions_data()` first)
    """
    if not path.exists():
        return GroupBinds(set())

    with path.open("rb") as f:
        group_binds = GroupBinds.model_validate_json(f.read())

    return group_binds


def load_data():
    """
    Loads the datas from previously saved files and add them to the cache.
    `load_config(...)` needs to be called first.
    """
    cache.already_parsed = load_already_parsed(ALREADY_PARSED_PATH)
    cache.transactions = load_transactions_data(TRANSACTIONS_PATH)
    cache.group_binds = load_binds_data(GROUP_BINDS)


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


def load_readers(readers_path: Path):
    """
    Looks at all .py files in the given directory and get the Reader class from the `export()` function.
    """
    readers: list[type[ReaderABC]] = []

    for reader_path in (readers_path).glob("*.py"):
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

    return readers


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


def parse_transactions(paths: PathsOptions):
    """
    Reads all the files in the 'exports' folder, detects the correct Reader, and uses it to add the new Transactions
    into the cache.
    """
    readers: list[type[ReaderABC]] = load_readers(paths.readers)

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


# Cache loader


def load_cache(paths: PathsOptions):
    """
    Will load the config and the data in the cache.
    """
    cache.paths = paths
    cache.banks = ValuesIterDict()  # dynamically built

    load_config()
    load_data()

    if cache.debug_mode:
        console.print(Markdown("# Banks"))
        console.print(cache.banks)
        console.print(Markdown("# Groups"))
        console.print(cache.groups)
        console.print(Markdown("# Grouping rules"))
        console.print(cache.grouping_rules)
        console.print(Markdown("# Accounts settings"))
        console.print(cache.accounts_settings)
        if Confirm.ask("Continue?"):
            console.clear()
        else:
            raise SystemExit(0)
