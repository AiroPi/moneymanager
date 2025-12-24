from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, RootModel

from .account import Account, Bank
from .cache import cache
from .group import GroupBind

if TYPE_CHECKING:
    from .group import Group


class Transaction(BaseModel):
    id: str
    bank_name: str = Field(alias="bank")
    account_name: str = Field(alias="account")
    amount: Decimal = Field(decimal_places=15)
    label: str
    date: date
    fee: Decimal | None = Field(default=None, decimal_places=15)
    _binds: set[GroupBind] = PrivateAttr(default_factory=set)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, value: object) -> bool:
        return isinstance(value, Transaction) and self.id == value.id

    def model_post_init(self, _: Any) -> None:
        if self.bank_name not in cache.banks:
            cache.banks[self.bank_name] = Bank(name=self.bank_name)
        if self.account_name not in self.bank.accounts:
            self.bank.add_account(Account(name=self.account_name))

        self.account.transactions.add(self)

    @property
    def groups(self) -> list[Group]:
        return [bind.group for bind in self._binds]

    def bind_group(self, group: Group, type: Literal["manual", "auto"]) -> None:
        cache.group_binds.new(self, group, type)

    @property
    def binds(self) -> set[GroupBind]:
        return self._binds

    @property
    def bank(self) -> Bank:
        return cache.banks[self.bank_name]

    @property
    def account(self) -> Account:
        return self.bank.accounts[self.account_name]


class Transactions(RootModel[set[Transaction]]):
    _mapped: dict[str, Transaction] = PrivateAttr(default_factory=dict)

    def __iter__(self):  # type: ignore
        return iter(self.root)

    def model_post_init(self, _: Any) -> None:
        for transaction in self.root:
            self._mapped[transaction.id] = transaction

    def get(self, key: str) -> Transaction | None:
        return self._mapped.get(key)

    def add(self, value: Transaction):
        self._mapped[value.id] = value
        self.root.add(value)

    def __getitem__(self, key: str) -> Transaction:
        return self._mapped[key]
