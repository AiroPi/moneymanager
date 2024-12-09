from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from .account import Bank
    from .accounts_settings import AccountsSettings
    from .group import AutoGroupRuleSets, Groups
    from .transaction import Transaction
    from .utils import ValuesIterDict


class Cache:
    instance: Self | None = None
    groups: Groups
    grouping_rules: list[AutoGroupRuleSets]
    accounts_settings: AccountsSettings
    transactions: set[Transaction]
    already_parsed: list[str]
    banks: ValuesIterDict[str, Bank]

    debug_mode: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        if cls.instance is None:
            cls.instance = super().__new__(cls, *args, **kwargs)
            # cls.instance.groups = Groups([])
            # cls.instance.grouping_rules = []
            # cls.accounts_settings = AccountsSettings(aliases={}, initial_values={})
            # cls.transactions = set()
        return cls.instance


cache = Cache()
