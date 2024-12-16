"""
# Export instructions

- Connect to https://particuliers.sg.fr/
- Go to https://particuliers.sg.fr/icd/gbi/index-gbi-authsec.html#/telecharger-operations
- Click the "download" button

Some efforts have also been made to be able to import transactions from an **account export** (not a **budget** export) without duplication.
If you encounter any problem, please fill an issue at https://github.com/AiroPi/moneymanager/issues.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from moneymanager.reader import ReaderABC, Transaction
from moneymanager.utils import fix_string

if TYPE_CHECKING:
    from moneymanager.reader import CSVReader


class SocieteGeneraleAccountExportReader(ReaderABC):
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
            label=self.get_label(row),
            date=datetime.strptime(row[0], r"%d/%m/%Y"),
        )

    def generate_id(self, row: list[str]):
        date = datetime.strptime(row[0], r"%d/%m/%Y")
        timestamp = int(date.timestamp())

        hasher = hashlib.md5()  # noqa: S324
        hasher.update(self.account.encode())
        hasher.update(self.get_label(row).encode())
        hasher.update(row[3].encode())
        hashed_rows = hasher.hexdigest()

        return self.fix_id(hashed_rows, timestamp)

    @staticmethod
    def header_match(header: str):
        return fix_string(header) == "Date de l'opération;Libellé;Détail de l'écriture;Montant de l'opération;Devise"

    @staticmethod
    def get_account(first_line: str):
        return first_line.split('"')[1][5:]

    @staticmethod
    def get_label(row: list[str]):
        if row[1].startswith("CARTE"):
            return " ".join(fix_string(row[2]).split(" ")[:-1])
        return fix_string(row[2])

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


class SocieteGeneraleBudgetExportReader(ReaderABC):
    def __init__(self, file: io.TextIOBase):
        super().__init__(file, header_lines=3)

    def generator(self, reader: CSVReader) -> Generator[Transaction]:
        for row in reader:
            yield self.row_parser(row)

    def row_parser(self, row: list[str]) -> Transaction:
        return Transaction(
            bank="Société Générale",
            account=row[2],
            id=self.generate_id(row),
            amount=Decimal(row[8].replace(",", ".")),
            label=fix_string(row[5]),
            date=datetime.strptime(row[0], r"%d/%m/%Y"),
        )

    def generate_id(self, row: list[str]):
        date = datetime.strptime(row[0], r"%d/%m/%Y")
        timestamp = int(date.timestamp())

        hasher = hashlib.md5()  # noqa: S324
        hasher.update(row[2].encode())
        hasher.update(fix_string(row[5]).encode())
        hasher.update(row[8].encode())
        hashed_rows = hasher.hexdigest()

        return self.fix_id(hashed_rows, timestamp)

    @staticmethod
    def header_match(header: str):
        return (
            fix_string(header)
            == "Date transaction;Date comptabilisation;Num Compte;Libellé Compte;Libellé opération;Libellé complet;Catégorie;Sous-Catégorie;Montant;Pointée;"
        )

    @classmethod
    def detect_file_impl(cls, file: io.BufferedReader):
        try:
            header = file.readline(300).decode(encoding="cp1252")
        except (UnicodeDecodeError, AttributeError):
            return None

        if cls.header_match(header):
            return cls(io.TextIOWrapper(file, encoding="cp1252"))
        return None


def export() -> list[type[ReaderABC]]:
    return [SocieteGeneraleAccountExportReader, SocieteGeneraleBudgetExportReader]
