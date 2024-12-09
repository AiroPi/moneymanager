from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from .cache import cache
from .utils import TransactionsAccessor, ValuesIterDict


class Bank(BaseModel):
    name: str
    accounts: ValuesIterDict[str, Account] = Field(default_factory=ValuesIterDict)

    def model_post_init(self, _: Any) -> None:
        self._transactions = TransactionsAccessor(self, "accounts")

    @property
    def transactions(self):
        return self._transactions

    def add_account(self, account: Account):
        self.accounts[account.name] = account
        account.bank = self


class Account(BaseModel):
    name: str
    _bank: Bank = PrivateAttr()

    def model_post_init(self, _: Any) -> None:
        self._transactions = TransactionsAccessor(self)

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
