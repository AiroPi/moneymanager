from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel

type AliasesT = dict[str, dict[str, str]]
type InitialValuesT = dict[str, dict[str, Decimal]]


class AccountsSettingsValidator(BaseModel):
    aliases: list[BankEntry[list[AccountAlias]]]
    initial_values: list[BankEntry[list[AccountInitialValue]]]


class BankEntry[T](BaseModel):
    bank: str
    values: T


class AccountAlias(BaseModel):
    input: str
    output: str


class AccountInitialValue(BaseModel):
    account: str
    value: Decimal


class AccountsSettings(BaseModel):
    aliases: AliasesT
    initial_values: InitialValuesT


def transform(accounts_settings: AccountsSettingsValidator):
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


def load_accounts_settings(path: Path) -> AccountsSettings:
    with path.open() as f:
        raw = yaml.safe_load(f)
    return transform(AccountsSettingsValidator.model_validate(raw))
