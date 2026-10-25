"""Exact bounded pure-function caching and conservative public-port read tracking."""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import EvaluateRequest, EvaluateResponse


class ParentEvaluateCache:
    """Per initialized instance; reuse only results already accepted by the Worker cache.

    A Worker cache hit proves that this exact input did not read execution identity,
    mutate managed state or exceed the response limit. Requiring that acknowledgement
    avoids adding a new wire field or trusting the pure_evaluate declaration alone.
    Parameters and initialization invalidate the cache; accepted state revisions,
    time, run/instance and every port field are part of the exact request key.
    The bound module hashes and fluid configuration belong to the instance lifetime.
    """

    def __init__(self) -> None:
        self.entries: OrderedDict[str, EvaluateResponse] = OrderedDict()
        self.hits = 0

    def clear(self) -> None:
        self.entries.clear()

    @staticmethod
    def key(request: EvaluateRequest) -> str | None:
        try:
            # model_dump_json maps nonfinite floats to null. Internal model_copy
            # trials may bypass validators; never let those alias a valid input.
            return json.dumps(request.model_dump(mode='json', exclude={'context', 'iteration_id'}),
                              ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (ValueError, TypeError, OverflowError):
            return None  # Preserve the Worker's normal input validation and diagnostics.

    def get(self, key: str) -> EvaluateResponse | None:
        cached = self.entries.get(key)
        if cached is None:
            return None
        self.entries.move_to_end(key)
        self.hits += 1
        return cached.model_copy(deep=True, update={'cache_hit': True})

    def remember(self, key: str, response: EvaluateResponse) -> None:
        # Bound key storage too: a module may have large input state or many ports.
        if (response.cache_hit and len(key.encode('utf-8')) <= 16384
                and len(response.model_dump_json().encode('utf-8')) <= 16384):
            self.entries[key] = response.model_copy(deep=True)
            self.entries.move_to_end(key)
            while len(self.entries) > 64:
                self.entries.popitem(last=False)


class GroupedModuleDifference:
    """Color module-residual columns once, then differentiate only their sparse rows.

    Columns can share a perturbation if no module equation depends on both. The
    pattern includes all module ports unless checked dependency tracking narrows it.
    No dense matrix is allocated, even when the enclosing solve requests sparse.
    """

    def __init__(self, pattern):
        import numpy as np

        columns = pattern.tocsc()
        self.shape = pattern.shape
        self.rows = [columns.indices[columns.indptr[col]:columns.indptr[col + 1]]
                     for col in range(pattern.shape[1])]
        groups, occupied = [], []
        for col in sorted(range(len(self.rows)), key=lambda c: -len(self.rows[c])):
            rows = set(self.rows[col])
            if not rows:
                continue
            for group, used in zip(groups, occupied):
                if rows.isdisjoint(used):
                    group.append(col)
                    used.update(rows)
                    break
            else:
                groups.append([col])
                occupied.append(rows)
        self.groups = [np.asarray(group, dtype=int) for group in groups]

    def evaluate(self, residual, vector, base):
        import numpy as np
        from scipy.sparse import csr_matrix

        rows, cols, data = [], [], []
        for group in self.groups:
            shifted = np.array(vector, dtype=float)
            shifted[group] += 1e-7 * np.maximum(1., np.abs(shifted[group]))
            delta = shifted - vector
            difference = residual(shifted) - base
            for col in group:
                indices = self.rows[col]
                values = difference[indices] / delta[col]
                rows.extend(indices)
                cols.extend([col] * len(indices))
                data.extend(values)
        matrix = csr_matrix((data, (rows, cols)), shape=self.shape)
        matrix.eliminate_zeros()
        return matrix


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
