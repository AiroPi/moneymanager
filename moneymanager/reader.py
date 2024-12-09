from __future__ import annotations

import abc
import csv
import importlib
import importlib.util
import io
from abc import abstractmethod
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from typing_extensions import TypeIs

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


def check_output_type(output: Any) -> TypeIs[list[type[ReaderABC]]]:
    if not isinstance(output, list):
        return False
    output = cast(list[Any], output)
    return all(issubclass(reader_cls, ReaderABC) for reader_cls in output)


def load_readers(readers_path: Path):
    readers: list[type[ReaderABC]] = []

    for reader_path in (readers_path).glob("*.py"):
        try:
            module = get_reader(reader_path)
        except ValueError as e:
            print(e)
            continue

        try:
            export: Callable[[], Any] = getattr(module, "export")
        except AttributeError:
            print(f"{reader_path} does not contains an 'export' function.")
            continue

        exported = export()
        if not check_output_type(exported):
            raise TypeError(f"{reader_path}' export function does not return a list of readers.")

        readers.extend(exported)

    return readers


def get_reader(path: Path):
    spec = importlib.util.spec_from_file_location(str(path), str(path))
    if not spec:
        raise ValueError(f"The file {path} cannot be imported.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore

    return module


def detect_reader(readers: list[type[ReaderABC]], file: io.BufferedReader) -> ReaderABC | None:
    for reader_cls in readers:
        if (reader := reader_cls.detect_file(file)) is not None:
            return reader
