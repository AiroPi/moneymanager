from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema


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
