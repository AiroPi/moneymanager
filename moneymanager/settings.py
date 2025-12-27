from __future__ import annotations

from decimal import Decimal
from typing import Any, Self, overload

from pydantic import BaseModel, Field, PrivateAttr, RootModel, model_validator

type AliasesT = dict[str, dict[str, str]]
type InitialValuesT = dict[str, dict[str, Decimal]]


class AccountsSettings(RootModel[list["BankSettings"]]):
    _map: dict[str, BankSettings] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _init_map(self) -> Self:
        for bank in self.root:
            if bank.bank_id in self._map:
                raise ValueError(f"Duplucate bank {bank.bank_id}")
            self._map[bank.bank_id] = bank

        return self

    def __getitem__(self, key: str) -> BankSettings:
        return self._map[key]

    @overload
    def get(self, bank_id: str, default: None = None, /) -> BankSettings | None: ...

    @overload
    def get[D: Any](self, bank_id: str, default: D, /) -> BankSettings | D: ...

    def get[D: Any](self, bank_id: str, default: D | None = None, /) -> BankSettings | None | D:
        """
        Get a bank by name in O(1).
        """
        return self._map.get(bank_id, default)


class BankSettings(BaseModel):
    bank_id: str
    display_name: str | None = None
    accounts: BankAccountsSettings = Field(default_factory=lambda: BankAccountsSettings([]))


class BankAccountsSettings(RootModel[list["BankAccountSettings"]]):
    _map: dict[str, BankAccountSettings] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _init_map(self) -> Self:
        for account in self.root:
            if account.account_id in self._map:
                raise ValueError(f"Duplicate account {account.account_id}")
            self._map[account.account_id] = account

        return self

    def __getitem__(self, key: str) -> BankAccountSettings:
        return self._map[key]

    @overload
    def get(self, account_id: str, default: None = None, /) -> BankAccountSettings | None: ...

    @overload
    def get[D: Any](self, account_id: str, default: D, /) -> BankAccountSettings | D: ...

    def get[D: Any](self, account_id: str, default: D | None = None, /) -> BankAccountSettings | None | D:
        """
        Get an account by name in O(1).
        """
        return self._map.get(account_id, default)


class BankAccountSettings(BaseModel):
    account_id: str
    display_name: str | None = None
    initial_balance: Decimal = Decimal(0)
