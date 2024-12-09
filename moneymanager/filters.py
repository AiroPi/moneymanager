from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

    from .transaction import Transaction


class Filter(ABC):
    @abstractmethod
    def test(self, transaction: Transaction) -> bool: ...


class BeforeFilter(Filter):
    def __init__(self, date: datetime) -> None:
        self.date = date

    def test(self, transaction: Transaction) -> bool:
        return transaction.date < self.date


class AfterFilter(Filter):
    def __init__(self, date: datetime) -> None:
        self.date = date

    def test(self, transaction: Transaction) -> bool:
        return transaction.date >= self.date


def filter_helper(
    before: datetime | None = None,
    after: datetime | None = None,
):
    filters: list[Filter] = []
    if before is not None:
        filters.append(BeforeFilter(before))
    if after is not None:
        filters.append(AfterFilter(after))
    return build_filter(filters)


def build_filter(filters: list[Filter]) -> Callable[[Iterable[Transaction]], Iterable[Transaction]]:
    def inner(transactions: Iterable[Transaction]) -> Iterable[Transaction]:
        for transaction in transactions:
            if all(filter.test(transaction) for filter in filters):
                yield transaction

    return inner
