"""
EDAstro Static Nebula Catalog & Spatial Membership Service.

Loads pre-formatted static SSOT data from app/data/nebulae/edastro_nebulae.json
and resolves whether a star system lies inside a known nebula (and its type)
purely offline via system/sector lookup and a 3D spatial hash grid.
"""

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.parser.bioscan.nebula_sectors import data as NEBULA_SECTORS

NEBULA_CATALOG_FILE = Path(__file__).resolve().parents[1] / "data" / "nebulae" / "edastro_nebulae.json"
_SPATIAL_BUCKET_LY = 60.0


@dataclass(frozen=True)
class _NebulaEntry:
    name: str
    system: str
    x: float
    y: float
    z: float
    ntype: str
    region_id: int
    radius_ly: float
    label_en: str
    label_ja: str


class _NebulaIndex:
    def __init__(self, catalog: Dict[str, Any]) -> None:
        types_meta: Dict[str, Dict[str, Any]] = catalog.get("types") or {}
        self.by_system: Dict[str, _NebulaEntry] = {}
        self.spatial_grid: Dict[Tuple[int, int, int], List[_NebulaEntry]] = defaultdict(list)
        self.by_sector_prefix: Dict[str, List[_NebulaEntry]] = defaultdict(list)

        known_sectors_lower = [s.lower() for s in NEBULA_SECTORS]

        for row in catalog.get("entries") or []:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            name = str(row[0]).strip()
            sys_raw = str(row[1]).strip()
            system = sys_raw if sys_raw else name
            try:
                x = float(row[2])
                y = float(row[3])
                z = float(row[4])
            except (ValueError, TypeError):
                continue
            ntype = str(row[5]).strip().lower()
            rid = int(row[6]) if len(row) > 6 and row[6] is not None else 0

            tmeta = types_meta.get(ntype) or {}
            label_en = str(tmeta.get("label_en") or ntype.title())
            label_ja = str(tmeta.get("label_ja") or label_en)

            sys_low = system.lower()
            name_low = name.lower()
            is_sector_nebula = (
                "sector" in sys_low
                or "dark region" in sys_low
                or "dark region" in name_low
                or any(sys_low.startswith(sec) for sec in known_sectors_lower)
            )
            if ntype == "real" and is_sector_nebula and "diffuse_radius_ly" in tmeta:
                radius_ly = float(tmeta["diffuse_radius_ly"])
            else:
                radius_ly = float(tmeta.get("radius_ly") or 5.0)

            entry = _NebulaEntry(
                name=name,
                system=system,
                x=x,
                y=y,
                z=z,
                ntype=ntype,
                region_id=rid,
                radius_ly=radius_ly,
                label_en=label_en,
                label_ja=label_ja,
            )

            self.by_system[sys_low] = entry

            bucket = _to_bucket(x, y, z)
            self.spatial_grid[bucket].append(entry)

            # Map sector prefixes (e.g. "Orion Sector", "Barnard's Loop Sector") to diffuse candidates
            for sec_low in known_sectors_lower:
                if sys_low.startswith(sec_low):
                    self.by_sector_prefix[sec_low].append(entry)
                else:
                    sec_base = sec_low.removesuffix(" sector").strip()
                    name_clean = name_low.removesuffix(" nebula").strip()
                    if sec_base and (name_clean == sec_base or name_low == sec_low):
                        self.by_sector_prefix[sec_low].append(entry)

        # Longest prefix checked first so e.g. "Horsehead Dark Region Sector" beats "Horsehead Sector"
        self.sorted_sector_prefixes: List[Tuple[str, List[_NebulaEntry]]] = sorted(
            self.by_sector_prefix.items(),
            key=lambda kv: len(kv[0]),
            reverse=True,
        )


def _to_bucket(x: float, y: float, z: float) -> Tuple[int, int, int]:
    return (
        int(math.floor(x / _SPATIAL_BUCKET_LY)),
        int(math.floor(y / _SPATIAL_BUCKET_LY)),
        int(math.floor(z / _SPATIAL_BUCKET_LY)),
    )


@lru_cache(maxsize=1)
def _get_nebula_index() -> Optional[_NebulaIndex]:
    if not NEBULA_CATALOG_FILE.exists():
        return None
    with NEBULA_CATALOG_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return _NebulaIndex(data)


def _parse_coords(
    x: Optional[float], y: Optional[float], z: Optional[float]
) -> Optional[Tuple[float, float, float]]:
    if x is None or y is None or z is None:
        return None
    try:
        fx, fy, fz = float(x), float(y), float(z)
    except (ValueError, TypeError):
        return None
    if not (math.isfinite(fx) and math.isfinite(fy) and math.isfinite(fz)):
        return None
    return (fx, fy, fz)


def _dist_ly(coords: Tuple[float, float, float], entry: _NebulaEntry) -> float:
    dx = coords[0] - entry.x
    dy = coords[1] - entry.y
    dz = coords[2] - entry.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _format_hit(
    entry: _NebulaEntry,
    match_method: str,
    distance_ly: Optional[float],
) -> Dict[str, Any]:
    return {
        "inside": True,
        "name": entry.name,
        "system": entry.system,
        "type": entry.ntype,
        "type_label_en": entry.label_en,
        "type_label_ja": entry.label_ja,
        "distance_ly": round(distance_ly, 1) if distance_ly is not None else None,
        "match_method": match_method,
    }


def find_nebula_for_system(
    star_system: Optional[str] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    z: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Determines whether a star system is inside a cataloged EDAstro nebula and identifies
    the nebula name and type without external network requests.

    Resolution order:
    1. Exact reference system name match (covers host stars of planetary & named nebulae)
    2. Official Elite nebula sector prefix match (cross-linked with EDAstro entries)
    3. 3D Euclidean coordinate containment within the nebula type's spatial radius

    Returns None when the system does not fall inside any cataloged nebula.
    """
    idx = _get_nebula_index()
    if idx is None:
        return None

    coords = _parse_coords(x, y, z)
    sys_clean = str(star_system).strip() if star_system else ""
    sys_low = sys_clean.lower()

    # 1. Exact reference system match
    if sys_low and sys_low in idx.by_system:
        entry = idx.by_system[sys_low]
        dist = _dist_ly(coords, entry) if coords is not None else 0.0
        return _format_hit(entry, "system", dist)

    # 2. Named nebula sector prefix match (e.g. "California Sector ...", "Orion Sector ...")
    if sys_low:
        for prefix, candidates in idx.sorted_sector_prefixes:
            if sys_low.startswith(prefix) and candidates:
                if coords is not None:
                    best = min(candidates, key=lambda c: _dist_ly(coords, c))
                    return _format_hit(best, "sector", _dist_ly(coords, best))
                return _format_hit(candidates[0], "sector", None)

    # 3. Spatial 3D containment check using 60 ly spatial hash neighborhood
    if coords is None:
        return None

    bx, by, bz = _to_bucket(*coords)
    best_entry: Optional[_NebulaEntry] = None
    best_dist: float = float("inf")

    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                bucket_entries = idx.spatial_grid.get((bx + dx, by + dy, bz + dz))
                if not bucket_entries:
                    continue
                for cand in bucket_entries:
                    d = _dist_ly(coords, cand)
                    if d <= cand.radius_ly and d < best_dist:
                        best_dist = d
                        best_entry = cand

    if best_entry is not None:
        return _format_hit(best_entry, "coords", best_dist)
    return None
