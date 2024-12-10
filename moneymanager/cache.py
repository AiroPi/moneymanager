from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from .account import Bank
    from .group import AutoGroupRuleSets, GroupBinds, Groups
    from .settings import AccountsSettings
    from .transaction import Transactions
    from .utils import ValuesIterDict


class Cache:
    instance: Self | None = None
    groups: Groups
    grouping_rules: list[AutoGroupRuleSets]
    accounts_settings: AccountsSettings
    transactions: Transactions
    already_parsed: list[str]
    banks: ValuesIterDict[str, Bank]
    group_binds: GroupBinds

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
