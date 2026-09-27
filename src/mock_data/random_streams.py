"""Stable per-entity random streams.

Every entity (site, asset, fault) gets its own ``numpy.random.Generator``
seeded from a hash of ``(global_seed, entity_key)``. This means regenerating
or reordering entities never perturbs another entity's draws — unlike a
single shared sequential RNG, where inserting/removing one record shifts
every draw downstream of it.
"""

from __future__ import annotations

import hashlib

import numpy as np


def stable_seed(global_seed: int, *parts: object) -> int:
    key = f"{global_seed}|" + "|".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") & 0x7FFFFFFFFFFFFFFF


def stream(global_seed: int, *parts: object) -> np.random.Generator:
    return np.random.default_rng(stable_seed(global_seed, *parts))


def weighted_choice(rng: np.random.Generator, options: list, weights: list[float]):
    total = sum(weights)
    probs = [w / total for w in weights]
    idx = rng.choice(len(options), p=probs)
    return options[idx]
