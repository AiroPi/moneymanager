from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, PrivateAttr

from .cache import cache
from .utils import ValuesIterDict

if TYPE_CHECKING:
    from .transaction import Transaction


class Bank(BaseModel):
    name: str
    accounts: ValuesIterDict[str, Account] = Field(default_factory=ValuesIterDict)

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

    @property
    def alias(self) -> str:
        return cache.accounts_settings.aliases.get(self.bank.name, {}).get(self.name, self.name)

    @property
    def transactions(self):
        return self._transactions

    @property
    def bank(self):
        return self._bank

    @bank.setter
    def bank(self, value: Bank):
        self._bank = value
