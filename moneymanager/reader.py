from __future__ import annotations

import abc
import csv
import io
from abc import abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .cache import cache
from .transaction import Transaction

if TYPE_CHECKING:
    from _csv import _reader  # type: ignore

    CSVReader = _reader


class ReaderABC(abc.ABC):
    def __init__(self, file: io.TextIOBase, delimiter: str = ";", header_lines: int = 1):
        self.file: io.TextIOBase = file
        self.ids: set[str] = set()
        self.delimiter = delimiter
        self.header_lines = header_lines

    def __enter__(self):
        reader = csv.reader(self.file, delimiter=self.delimiter)
        self.skip_headers(reader)

        return self.generator(reader)

    def __exit__(self, *exc_infos: object) -> bool | None:
        self.file.close()

    @classmethod
    def detect_file[R: ReaderABC](cls: type[R], file: io.BufferedReader) -> R | None:
        try:
            return cls.detect_file_impl(file)
        finally:
            file.seek(0)

    @classmethod
    @abstractmethod
    def detect_file_impl[R: ReaderABC](cls: type[R], file: io.BufferedReader) -> R | None: ...

    def skip_headers(self, reader: _reader):
        [next(reader) for _ in range(self.header_lines)]

    @abstractmethod
    def generator(self, reader: _reader) -> Iterable[Transaction]:
        pass

    def fix_id(self, hash_: str, timestamp: int) -> str:
        id_ = f"{hash_}.{timestamp:x}"
        incr = 0
        while id_ in self.ids:
            incr += 1
            id_ = f"{hash_}.{timestamp+incr:x}"

        self.ids.add(id_)

        return id_


def detect_reader(file: io.BufferedReader) -> ReaderABC | None:
    for reader_cls in cache.readers:
        if (reader := reader_cls.detect_file(file)) is not None:
            return reader
