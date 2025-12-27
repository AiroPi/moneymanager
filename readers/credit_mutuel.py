"""
# Export instructions

- Connect to [https://www.creditmutuel.fr/](https://www.creditmutuel.fr/)
- Go to [https://www.creditmutuel.fr/fr/banque/compte/telechargement.cgi](https://www.creditmutuel.fr/fr/banque/compte/telechargement.cgi)
- Select OFX format, with "Money 2003 et suivants"
- **Uncheck** the box "Je souhaite que le libellé des opérations soit affecté à la zone 'Tiers' de mon logiciel."
- Select all the accounts you want to import, the click "Téléchargez toutes les opérations disponibles" and "Télécharger"

If you encounter any problem, please fill an issue at [https://github.com/AiroPi/moneymanager/issues](https://github.com/AiroPi/moneymanager/issues).

"""

from __future__ import annotations

import io
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from moneymanager import Transaction
from moneymanager.reader import ReaderABC
from moneymanager.ui import (
    Markdown,
    console,
)

if TYPE_CHECKING:
    from ofxtools.models.bank.stmt import STMTTRN
    from ofxtools.models.base import Aggregate

    class STMTTRNTyped(STMTTRN):
        fitid: str
        trnamt: Decimal
        memo: str
        name: str
        dtposted: datetime


class CreditMutuelOFXReader(ReaderABC):
    def __init__(self, file: io.BufferedReader):
        self.file = file

    def __enter__(self):
        try:
            from ofxtools.Parser import OFXTree
        except ImportError:
            console.print(
                Markdown(
                    "This reader needs `ofxtools` to be installed, you should install the optional dependency `ofx` when installing `moneymanager` !"
                )
            )
            raise

        parser = OFXTree()
        parser.parse(self.file)
        ofx = parser.convert()

        return self.generator(ofx)

    def generator(self, ofx: Aggregate) -> Generator[Transaction]:
        for statement in ofx.statements:
            bank_id = statement.bankid
            acc_id = statement.acctid

            for transaction in statement.transactions:
                yield self.convert_transaction(transaction, bank_id, acc_id)

    def convert_transaction(self, transaction: STMTTRNTyped, bank_id: str, acc_id: str) -> Transaction:
        return Transaction(
            bank=bank_id,
            account=acc_id,
            amount=transaction.trnamt,
            label=transaction.name or transaction.memo,
            date=transaction.dtposted.date(),
            id=transaction.fitid,
        )

    @classmethod
    def detect_file_impl(cls, file: io.BufferedReader) -> CreditMutuelOFXReader | None:
        try:
            header = file.readline(300).decode()
        except (UnicodeDecodeError, AttributeError):
            return None

        if "OFXHEADER" not in header:
            return None

        for _ in range(100):
            line = file.readline(300).decode()
            if "BANKID" in line and "10278" in line:
                file.seek(0)
                return cls(file)

        return None


def export() -> list[type[ReaderABC]]:
    return [CreditMutuelOFXReader]
