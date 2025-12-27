from __future__ import annotations

import abc
import csv
import io
from abc import abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, ClassVar

from .cache import cache

if TYPE_CHECKING:
    from _csv import _reader  # type: ignore

    from .transaction import Transaction

    CSVParser = _reader


class ReaderABC(abc.ABC):
    def __init__(self, file: io.IOBase):
        self.file = file

    @abstractmethod
    def __enter__(self) -> Iterable[Transaction]: ...

    def __exit__(self, *exc_infos: object) -> bool | None:
        self.file.close()

    @classmethod
    @abstractmethod
    def detect_file_impl[R: ReaderABC](cls: type[R], file: io.BufferedReader) -> R | None: ...

    @abstractmethod
    def generator(self, *args: Any, **kwargs: Any) -> Iterable[Transaction]: ...


class CSVReader(ReaderABC):
    delimiter: ClassVar = ";"
    header_lines: ClassVar = 1

    def __init__(self, file: io.TextIOBase):
        self.file: io.TextIOBase = file
        self.ids: set[str] = set()

    def __enter__(self) -> Iterable[Transaction]:
        reader = csv.reader(self.file, delimiter=self.delimiter)
        self.skip_headers(reader)

        return self.generator(reader)

    def skip_headers(self, reader: CSVParser):
        [next(reader) for _ in range(self.header_lines)]

    def generator(self, reader: CSVParser) -> Iterable[Transaction]:
        for row in reader:
            yield self.row_parser(row)

    @abstractmethod
    def row_parser(self, row: list[str]) -> Transaction: ...

    def fix_id(self, hash_: str, timestamp: int) -> str:
        id_ = f"{hash_}.{timestamp:x}"
        incr = 0
        while id_ in self.ids:
            incr += 1
            id_ = f"{hash_}.{timestamp + incr:x}"

        self.ids.add(id_)

        return id_


def detect_file[R: ReaderABC](reader: type[R], file: io.BufferedReader) -> R | None:
    try:
        return reader.detect_file_impl(file)
    finally:
        file.seek(0)


def detect_reader(file: io.BufferedReader) -> ReaderABC | None:
    for reader_cls in cache.readers:
        if (reader := detect_file(reader_cls, file)) is not None:
            return reader
