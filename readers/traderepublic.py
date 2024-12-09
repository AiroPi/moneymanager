"""
Export instructions:

- install the "pytr" python module
- use the commande "pytr dl_docs *path*
- take the account_transactions.csv file out of all the files
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Self

from moneymanager.reader import ReaderABC, Transaction
from moneymanager.utils import fix_string

if TYPE_CHECKING:
    from moneymanager.reader import CSVReader


class TradeRepublicReader(ReaderABC):
    def generator(self, reader: CSVReader) -> Generator[Transaction]:
        for row in reader:
            yield from self.row_parser(row)

    def row_parser(self, row: list[str]) -> Generator[Transaction]:
        yield Transaction(
            bank="Trade Republic",
            account="Cash",
            id=self.generate_id(row),
            amount=Decimal(row[2].replace(",", "")),
            label=row[3],
            date=datetime.strptime(row[0], r"%Y-%m-%d"),
            fee=Decimal(row[6]) if row[6] else None,
        )

    def generate_id(self, row: list[str], fee: bool = False) -> str:
        date = datetime.strptime(row[0], r"%Y-%m-%d")
        timestamp = int(date.timestamp())

        hasher = hashlib.md5()  # noqa: S324
        hasher.update(row[0].encode())
        hasher.update(row[1].encode())
        hasher.update(row[2].encode())
        hasher.update(row[3].encode())
        hasher.update(row[4].encode())
        hasher.update(row[5].encode())

        if fee:
            hasher.update(row[6].encode())

        hashed_rows = hasher.hexdigest()

        return self.fix_id(hashed_rows, timestamp)

    @staticmethod
    def header_match(header: str) -> bool:
        return fix_string(header) == "Date;Type;Value;Note;ISIN;Shares;Fees;Taxes"

    @classmethod
    def detect_file_impl(cls, file: io.BufferedReader) -> Self | None:
        try:
            header = file.readline(300).decode(encoding="utf-8")
        except (UnicodeDecodeError, AttributeError):
            return None

        if cls.header_match(header):
            return cls(io.TextIOWrapper(file, encoding="utf-8"))
        return None


def export() -> list[type[ReaderABC]]:
    return [TradeRepublicReader]
