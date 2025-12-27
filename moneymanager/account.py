from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from functools import cached_property
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, PrivateAttr

from .cache import cache
from .utils import ValuesIterDict

if TYPE_CHECKING:
    from moneymanager.settings import BankAccountSettings, BankSettings

    from .transaction import Transaction


class Bank(BaseModel):
    name: str
    accounts: ValuesIterDict[str, Account] = Field(default_factory=ValuesIterDict)

    @cached_property
    def settings(self) -> BankSettings | None:
        return cache.accounts_settings.get(self.name)

    @property
    def display_name(self) -> str:
        if self.settings:
            return self.settings.display_name or self.name
        return self.name

    @property
    def transactions(self) -> Iterator[Transaction]:
        for account in self.accounts:
            yield from account.transactions

    def add_account(self, account: Account):
        self.accounts[account.name] = account
        account.bank = self


class Account(BaseModel):
    name: str
    _bank: Bank = PrivateAttr()
    _transactions: set[Transaction] = PrivateAttr(default_factory=set)

    def __hash__(self) -> int:
        return hash(self._bank.name + self.name)

    @cached_property
    def settings(self) -> BankAccountSettings | None:
        return self._bank.settings and self._bank.settings.accounts.get(self.name)

    @property
    def display_name(self) -> str:
        if self.settings:
            return self.settings.display_name or self.name
        return self.name

    @property
    def initial_balance(self) -> Decimal:
        if self.settings:
            return self.settings.initial_balance
        return Decimal(0)

    @property
    def transactions(self) -> set[Transaction]:
        return self._transactions

    @property
    def bank(self) -> Bank:
        return self._bank

    @bank.setter
    def bank(self, value: Bank) -> None:
        self._bank = value
