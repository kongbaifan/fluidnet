"""Exact bounded pure-function caching and conservative public-port read tracking."""
from collections.abc import Mapping


class TrackedPorts(Mapping):
    def __init__(self, values, accessed):
        self._values, self.accessed = values, accessed

    def __getitem__(self, key):
        self.accessed.add(key)
        return self._values[key]

    def __iter__(self):
        self.accessed.update(self._values)
        return iter(self._values)

    def __len__(self):
        return len(self._values)
