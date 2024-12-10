from __future__ import annotations

from decimal import Decimal

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
