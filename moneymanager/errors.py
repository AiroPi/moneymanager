from collections.abc import Sequence
from pathlib import Path


class MissingConfigFile(Exception):
    def __init__(self, paths: Sequence[Path]):
        self.paths = paths
