from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, cast, overload

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

    from .transaction import Transaction


class SorterType(Enum):
    DATE = auto()


class SorterOrder(Enum):
    ASC = auto()
    DESC = auto()


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


class SliceFilter:
    @overload
    def __init__(self, *, first: int) -> None: ...
    @overload
    def __init__(self, *, last: int) -> None: ...

    def __init__(self, *, first: int | None = None, last: int | None = None) -> None:
        if first is not None:
            self._slice = slice(first)
        else:
            self._slice = slice(-cast(int, last), None)

    def __call__(self, transactions: Sequence[Transaction]) -> Sequence[Transaction]:
        return transactions[self._slice]


class Sorter:
    def __init__(self, sorter_func: Callable[[Transaction], Any], reverse: bool):
        self.sorter_func = sorter_func
        self.reverse = reverse

    def __call__(self, transactions: Iterable[Transaction]) -> Sequence[Transaction]:
        return sorted(transactions, key=self.sorter_func, reverse=self.reverse)


def filter_helper(
    *,
    sorter_type: SorterType = SorterType.DATE,
    sorter_order: SorterOrder = SorterOrder.ASC,
    before: datetime | None = None,
    after: datetime | None = None,
    first: int | None = None,
    last: int | None = None,
):
    filters: list[Filter] = []
    slice_filter: None | SliceFilter = None
    if before is not None:
        filters.append(BeforeFilter(before))
    if after is not None:
        filters.append(AfterFilter(after))
    if first is not None:
        slice_filter = SliceFilter(first=first)
    if last is not None:
        slice_filter = SliceFilter(last=last)

    _sorter_functions: dict[SorterType, Callable[[Transaction], Any]] = {
        SorterType.DATE: lambda t: t.date,
    }
    sorter_func = _sorter_functions[sorter_type]
    sorter = Sorter(sorter_func, sorter_order is SorterOrder.DESC)

    return build_filter(filters, sorter, slice_filter)


def build_filter(
    filters: list[Filter], sorter: Sorter, slice_filter: SliceFilter | None
) -> Callable[[Iterable[Transaction]], Sequence[Transaction]]:
    def pre_sort(transactions: Iterable[Transaction]) -> Iterable[Transaction]:
        for transaction in transactions:
            if all(filter.test(transaction) for filter in filters):
                yield transaction

    def post_sort(transactions: Sequence[Transaction]) -> Sequence[Transaction]:
        if slice_filter:
            return slice_filter(transactions)
        return transactions

    def inner(transactions: Iterable[Transaction]) -> Sequence[Transaction]:
        return post_sort(sorter(pre_sort(transactions)))

    return inner
