"""Read footprints packs: one place's buildings in a single compact file.

Packs are written by web/footprints/lib/footprints-data.js (the web page, the cache
function and the prepared-cities builder share it); see that file for the format.
Rings are in metres from the pack's centre, north up, wound so courtyards are holes
under the nonzero fill rule.
"""
from __future__ import annotations

import gzip
import json
import struct
from pathlib import Path

MAGIC = b"FPK1"


def _varints(data: bytes, pos: int):
    while True:
        result, shift = 0, 0
        while True:
            b = data[pos]
            pos += 1
            result |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
        yield result


def read(source) -> tuple[dict, list[list[tuple[float, float]]]]:
    data = Path(source).read_bytes() if not isinstance(source, (bytes, bytearray)) else bytes(source)
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if data[:4] != MAGIC:
        raise ValueError("Not a footprints pack")
    (length,) = struct.unpack_from("<I", data, 4)
    header = json.loads(data[8:8 + length])
    unit = header.get("unit", 0.2)
    numbers = _varints(data, 8 + length)
    unzag = lambda n: -(n + 1) // 2 if n & 1 else n // 2
    rings, cx, cy = [], 0, 0
    for _ in range(next(numbers)):
        ring = []
        for _ in range(next(numbers)):
            cx += unzag(next(numbers))
            cy += unzag(next(numbers))
            ring.append((cx * unit, cy * unit))
        rings.append(ring)
    return header, rings
