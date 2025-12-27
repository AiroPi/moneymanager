from __future__ import annotations

from typing import TYPE_CHECKING, Any, Never, Self

if TYPE_CHECKING:
    from .account import Bank
    from .group import GroupBinds, Groups
    from .loaders import MoneymanagerPaths
    from .reader import ReaderABC
    from .settings import AccountsSettings
    from .transaction import Transactions
    from .utils import ValuesIterDict


_unloaded: Any = object()


class UnloadedCacheAccess(Exception):
    pass


class Cache:
    """
    Singleton class that contains all the data the app can access during its process.
    Technically, this could be replaced by contextvars. (I didn't know it exists).
    But, making my own cache avoids conflicts, and allow asynchrone as well.
    """

    instance: Self | None = None
    paths: MoneymanagerPaths = _unloaded
    groups: Groups = _unloaded
    accounts_settings: AccountsSettings = _unloaded
    transactions: Transactions = _unloaded
    already_parsed: list[str] = _unloaded
    banks: ValuesIterDict[str, Bank] = _unloaded
    group_binds: GroupBinds = _unloaded
    readers: list[type[ReaderABC]] = _unloaded

    debug_mode: bool = False
    dry_run: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        if cls.instance is None:
            cls.instance = super().__new__(cls, *args, **kwargs)
        return cls.instance

    def is_loaded(self, name: str):
        return super().__getattribute__(name) is not _unloaded

    def __getattribute__(self, name: str) -> object:
        value = super().__getattribute__(name)
        if value is _unloaded:
            raise UnloadedCacheAccess("You are trying to access a non-loaded value!")
        return value

    def __getattr__(self, name: str) -> Never:
        raise AttributeError(
            f"{name} is not loaded in the cache. Call the associated loader first (maybe you messed up "
            "with the load order?)"
        )


cache = Cache()
