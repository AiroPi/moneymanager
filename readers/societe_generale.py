from __future__ import annotations

import hashlib
import io
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal

# from decimal import Decimal
from typing import TYPE_CHECKING

from moneymanager.reader import ReaderABC, Transaction
from moneymanager.utils import fix_string

if TYPE_CHECKING:
    from moneymanager.reader import CSVReader


class SocieteGeneraleReader(ReaderABC):
    def __init__(self, file: io.TextIOBase, account: str):
        super().__init__(file, header_lines=3)
        self.account = account

    def generator(self, reader: CSVReader) -> Generator[Transaction]:
        for row in reader:
            yield self.row_parser(row)

    def row_parser(self, row: list[str]) -> Transaction:
        return Transaction(
            bank="Société Générale",
            account=self.account,
            id=self.generate_id(row),
            amount=Decimal(row[3].replace(",", ".")),
            label=row[2],
            date=datetime.strptime(row[0], r"%d/%m/%Y"),
        )

    def generate_id(self, row: list[str]):
        date = datetime.strptime(row[0], r"%d/%m/%Y")
        timestamp = int(date.timestamp())

        hasher = hashlib.md5()  # noqa: S324
        hasher.update(row[1].encode())
        hasher.update(row[2].encode())
        hasher.update(row[3].encode())
        hasher.update(row[4].encode())
        hashed_rows = hasher.hexdigest()

        return self.fix_id(hashed_rows, timestamp)

    @staticmethod
    def header_match(header: str):
        return fix_string(header) == "Date de l'opération;Libellé;Détail de l'écriture;Montant de l'opération;Devise"

    @staticmethod
    def get_account(first_line: str):
        return first_line.split('"')[1]

    @classmethod
    def detect_file_impl(cls, file: io.BufferedReader):
        try:
            first_line = file.readline(300).decode(encoding="cp1252")
            file.readline(300)
            header = file.readline(300).decode(encoding="cp1252")
        except (UnicodeDecodeError, AttributeError):
            return None

        if cls.header_match(header):
            return cls(io.TextIOWrapper(file, encoding="cp1252"), cls.get_account(first_line))
        return None


def export() -> list[type[ReaderABC]]:
    return [SocieteGeneraleReader]
