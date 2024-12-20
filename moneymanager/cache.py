from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from .account import Bank
    from .group import GroupBinds, GroupingRules, Groups
    from .loaders import PathsOptions
    from .reader import ReaderABC
    from .settings import AccountsSettings
    from .transaction import Transactions
    from .utils import ValuesIterDict


class Cache:
    """
    Singleton class that contains all the data the app can access during its process.
    Technically, this could be replaced by contextvars. (I didn't know it exists).
    But, making my own cache avoids conflicts, and allow asynchrone as well.
    """

    instance: Self | None = None
    paths: PathsOptions
    groups: Groups
    grouping_rules: GroupingRules
    accounts_settings: AccountsSettings
    transactions: Transactions
    already_parsed: list[str]
    banks: ValuesIterDict[str, Bank]
    group_binds: GroupBinds
    readers: list[type[ReaderABC]]

    debug_mode: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        if cls.instance is None:
            cls.instance = super().__new__(cls, *args, **kwargs)
        return cls.instance

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            f"{name} is not loaded in the cache. Call the associated loader first (maybe you messed up "
            "with the load order?)"
        )


cache = Cache()
