from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, RootModel

from .account import Account, Bank
from .cache import cache

if TYPE_CHECKING:
    from .group import Group


class Transaction(BaseModel):
    id: str
    bank_name: str = Field(alias="bank")
    account_name: str = Field(alias="account")
    amount: Decimal
    label: str
    date: datetime
    fee: Decimal | None = None
    groups_names: set[str] = Field(default_factory=set)

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
        return [cache.groups[group_name] for group_name in self.groups_names]

    def bind_group(self, group: Group) -> None:
        self.groups_names.add(group.name)
        group.transactions.add(self)

    @property
    def bank(self) -> Bank:
        return cache.banks[self.bank_name]

    @property
    def account(self) -> Account:
        return self.bank.accounts[self.account_name]


class Transactions(RootModel[set[Transaction]]): ...


def load_transactions(path: Path) -> set[Transaction]:
    if not path.exists():
        return set()

    with path.open(encoding="utf-8") as f:
        transactions = Transactions.model_validate_json(f.read())

    for transaction in transactions.root:
        for group in transaction.groups:
            group.transactions.add(transaction)

    return transactions.root
