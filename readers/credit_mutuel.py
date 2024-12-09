"""
Export instructions:

- Connect to https://www.creditmutuel.fr/
- Go to https://www.creditmutuel.fr/fr/banque/budget.html#/pfm/transactions
- In the "Paramètres" tab, select all the accounts you want to include (probably all of your accounts)
- in the "Opérations" tab, click the "download" icon
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal

# from decimal import Decimal
from typing import TYPE_CHECKING, Never

from moneymanager.reader import ReaderABC, Transaction
from moneymanager.utils import fix_string

if TYPE_CHECKING:
    from moneymanager.reader import CSVReader


class CreditMutuelReader(ReaderABC):
    def generator(self, reader: CSVReader) -> Generator[Transaction]:
        for row in reader:
            yield self.row_parser(row)

    def row_parser(self, row: list[str]) -> Transaction:
        return Transaction(
            bank=row[0],
            account=row[1],
            amount=Decimal(row[13].replace(",", ".")),
            label=row[8],
            date=datetime.strptime(row[6], r"%d/%m/%Y"),
            id=self.generate_id(row),
        )

    def generate_id(self, row: list[str]) -> str:
        date = datetime.strptime(row[6], r"%d/%m/%Y")
        timestamp = int(date.timestamp())

        hasher = hashlib.md5()  # noqa: S324
        hasher.update(row[0].encode())
        hasher.update(row[1].encode())
        hasher.update(row[2].encode())
        hasher.update(row[8].encode())
        hasher.update(row[13].encode())
        hasher.update(row[14].encode())
        hashed_rows = hasher.hexdigest()

        return self.fix_id(hashed_rows, timestamp)

    @staticmethod
    def header_match(header: str) -> bool:
        return (
            fix_string(header)
            == "Banque;Libellé Compte;RIB;Type carte;Porteur;N° carte;Date opération;Date prise en compte;Libellé opération;Note personnelle;Type opération;Catégorie;Sous-catégorie;Montant;Devise;Opération pointée;Tags associés"
        )

    @classmethod
    def detect_file_impl(cls, file: io.BufferedReader) -> CreditMutuelReader | None:
        try:
            header = file.readline(300).decode()
        except (UnicodeDecodeError, AttributeError):
            return None

        if cls.header_match(header):
            return cls(io.TextIOWrapper(file))
        return None


class CreditMutuelReader2(ReaderABC):
    def __enter__(self) -> Never:
        raise ValueError

    @staticmethod
    def header_match(header: str) -> bool:
        return fix_string(header) == "Date;Date de valeur;Montant;Libellé;Solde"

    @classmethod
    def detect_file_impl(cls, file: io.BufferedReader) -> CreditMutuelReader2 | None:
        try:
            header = file.readline(300).decode("cp1252")
        except (UnicodeDecodeError, AttributeError):
            return None

        if cls.header_match(header):
            raise ValueError(
                "Detected bad export for Crédit Mutuel : please export your operations at https://www.creditmutuel.fr/fr/banque/budget.html#/pfm/transactions instead."
            )
        return None


def export() -> list[type[ReaderABC]]:
    return [CreditMutuelReader, CreditMutuelReader2]
