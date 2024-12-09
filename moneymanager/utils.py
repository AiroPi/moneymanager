from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

if TYPE_CHECKING:
    from .transaction import Transaction


def fix_string(string: str):
    string = string.strip()
    string = string.encode().decode("utf-8-sig")
    return string


def format_amount(amount: float | Decimal):
    color = "[red]" if amount < 0 else "[green]"
    return f"{color}{amount:,.2f}€"


class ValuesIterDict[K, T](dict[K, T]):
    def __iter__(self):  # type: ignore
        yield from self.values()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.no_info_after_validator_function(cls, handler(dict))


class HasTransactions(Protocol):
    @property
    def transactions(self) -> TransactionsAccessor: ...


class TransactionsAccessor(set["Transaction"]):
    def __init__(self, group: HasTransactions, recursive_access: str | None = None) -> None:
        self.group = group
        self.recursive_access = recursive_access
        super().__init__()

    def all(self) -> Iterator[Transaction]:
        yield from self._iter(set())

    def _iter(self, deduplicate: set[Transaction]) -> Iterator[Transaction]:
        for transaction in super().__iter__():
            if transaction in deduplicate:
                continue
            deduplicate.add(transaction)
            yield transaction

        if self.recursive_access and hasattr(self.group, self.recursive_access):
            for subgroup in getattr(self.group, self.recursive_access):
                yield from subgroup.transactions._iter(deduplicate)
