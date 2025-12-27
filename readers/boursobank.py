"""
# Export instructions

- Connect to [https://boursobank.com](https://boursobank.com)
- Go to [https://clients.boursobank.com/operations/generate](https://clients.boursobank.com/operations/generate)
- Select your account(s)
- Select a period (can overlap with the previous exports)
- Chose "CSV"
- Export
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime
from decimal import Decimal
from typing import Self

from moneymanager import Transaction
from moneymanager.reader import CSVReader, ReaderABC
from moneymanager.utils import fix_string


class BoursoBankReader(CSVReader):
    def row_parser(self, row: list[str]) -> Transaction:
        return Transaction(
            bank=row[8],
            account=row[7],
            id=self.generate_id(row),
            amount=Decimal(row[5].replace(",", ".").replace(" ", "")),
            label=row[2],
            date=datetime.strptime(row[0], r"%Y-%m-%d"),
        )

    def generate_id(self, row: list[str]) -> str:
        date = datetime.strptime(row[0], r"%Y-%m-%d")
        timestamp = int(date.timestamp())

        hasher = hashlib.md5()  # noqa: S324
        hasher.update(row[0].encode())
        hasher.update(row[1].encode())
        hasher.update(row[2].encode())
        hasher.update(row[5].encode())
        hasher.update(row[7].encode())
        hasher.update(row[8].encode())
        hasher.update(row[9].encode())
        hashed_rows = hasher.hexdigest()

        return self.fix_id(hashed_rows, timestamp)

    @staticmethod
    def header_match(header: str) -> bool:
        return (
            fix_string(header)
            == "dateOp;dateVal;label;category;categoryParent;amount;comment;accountNum;accountLabel;accountbalance"
        )

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
    return [BoursoBankReader]
