"""
Galactic Region & Sector Exploration Progress Service.

Aggregates visited systems, distinct explored sectors, body scan coverage, and
visited grid coordinates across the 42 official Galactic Regions without adding
heavy datasets or external network calls.
"""

import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.services.landmark_service import load_landmarks
from app.utils.galactic_regions import (
    GALACTIC_REGIONS,
    coords_to_grid_cell,
    find_region_id,
    get_region_info,
    get_region_map_grid,
)
from app.utils.voxel import extract_sector_name


def _resolve_region_id(x: Optional[float], z: Optional[float]) -> Optional[int]:
    if x is None or z is None:
        return None
    rid = find_region_id(x, z)
    return rid if rid in GALACTIC_REGIONS else None


def get_regions_overview(
    conn: sqlite3.Connection,
    current_coords: Optional[Tuple[Optional[float], Optional[float], Optional[float]]] = None,
) -> Dict[str, Any]:
    """
    Returns summary statistics for all 42 Galactic Regions plus compact visited grid cells
    and landmark map positions for lightweight Galaxy Region Map rendering.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT star_system, star_pos_x, star_pos_z,
               visit_count, total_bodies, scanned_bodies,
               has_elw, has_water_world, is_external, last_visited
        FROM systems
        WHERE star_pos_x IS NOT NULL AND star_pos_z IS NOT NULL
        """
    )

    stats: Dict[int, Dict[str, Any]] = {
        rid: {
            "region_id": rid,
            "name_en": names[0],
            "name_ja": names[1],
            "visited_systems": 0,
            "external_systems": 0,
            "sector_set": set(),
            "total_visits": 0,
            "scanned_bodies": 0,
            "total_bodies": 0,
            "elw_count": 0,
            "ww_count": 0,
            "last_visited": "",
        }
        for rid, names in sorted(GALACTIC_REGIONS.items())
    }
    visited_cells: Dict[Tuple[int, int], int] = defaultdict(int)

    for row in cur.fetchall():
        sx, sz = row["star_pos_x"], row["star_pos_z"]
        rid = _resolve_region_id(sx, sz)
        if rid is None:
            continue
        bucket = stats[rid]
        is_ext = int(row["is_external"] or 0)
        if is_ext:
            bucket["external_systems"] += 1
            continue

        bucket["visited_systems"] += 1
        bucket["total_visits"] += int(row["visit_count"] or 0)
        bucket["scanned_bodies"] += int(row["scanned_bodies"] or 0)
        bucket["total_bodies"] += int(row["total_bodies"] or 0)
        bucket["elw_count"] += 1 if row["has_elw"] else 0
        bucket["ww_count"] += 1 if row["has_water_world"] else 0
        lv = row["last_visited"] or ""
        if lv > bucket["last_visited"]:
            bucket["last_visited"] = lv

        sector = extract_sector_name(row["star_system"])
        if sector:
            bucket["sector_set"].add(sector)

        cell = coords_to_grid_cell(sx, sz)
        if cell is not None:
            visited_cells[cell] += 1

    regions_list: List[Dict[str, Any]] = []
    total_visited_systems = 0
    total_sectors = 0
    explored_regions = 0
    for rid in sorted(stats.keys()):
        b = stats[rid]
        sec_cnt = len(b.pop("sector_set"))
        b["sector_count"] = sec_cnt
        total_visited_systems += b["visited_systems"]
        total_sectors += sec_cnt
        if b["visited_systems"] > 0:
            explored_regions += 1
        regions_list.append(b)

    # Landmarks plotted onto grid coordinates (SSOT from app/data/landmarks.json)
    landmarks_out: List[Dict[str, Any]] = []
    raw_landmarks = load_landmarks()
    lm_iter = raw_landmarks.values() if isinstance(raw_landmarks, dict) else raw_landmarks
    for lm in lm_iter:
        if not isinstance(lm, dict):
            continue
        coords = lm.get("coords")
        if not isinstance(coords, (list, tuple)) or len(coords) < 3:
            continue
        cell = coords_to_grid_cell(coords[0], coords[2])
        if cell is None:
            continue
        landmarks_out.append({
            "name": lm.get("name") or lm.get("system_name") or "",
            "system_name": lm.get("system_name") or "",
            "gx": cell[0],
            "gz": cell[1],
            "region_id": _resolve_region_id(coords[0], coords[2]),
        })

    cur_loc_meta: Optional[Dict[str, Any]] = None
    if current_coords and current_coords[0] is not None and current_coords[2] is not None:
        cx, _, cz = current_coords
        cell = coords_to_grid_cell(cx, cz)
        rid = _resolve_region_id(cx, cz)
        if cell is not None or rid is not None:
            r_info = get_region_info(rid) if rid is not None else None
            cur_loc_meta = {
                "gx": cell[0] if cell else None,
                "gz": cell[1] if cell else None,
                "region_id": r_info[0] if r_info else None,
                "name_en": r_info[1] if r_info else None,
                "name_ja": r_info[2] if r_info else None,
            }

    return {
        "grid": get_region_map_grid(8),
        "regions": regions_list,
        "visited_cells": [[gx, gz, cnt] for (gx, gz), cnt in sorted(visited_cells.items())],
        "landmarks": landmarks_out,
        "current_location": cur_loc_meta,
        "summary": {
            "total_regions": len(GALACTIC_REGIONS),
            "explored_regions": explored_regions,
            "total_visited_systems": total_visited_systems,
            "total_sectors": total_sectors,
        },
    }


def get_region_sectors(conn: sqlite3.Connection, region_id: int) -> Optional[Dict[str, Any]]:
    """
    Returns exploration progress grouped by Sector name within the requested Galactic Region.
    Returns None when region_id is not one of the 42 official Galactic Regions.
    """
    if region_id not in GALACTIC_REGIONS:
        return None
    rid, name_en, name_ja = get_region_info(region_id)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT system_address, star_system, star_pos_x, star_pos_z,
               visit_count, total_bodies, scanned_bodies,
               has_elw, has_water_world, is_external, last_visited
        FROM systems
        WHERE star_pos_x IS NOT NULL AND star_pos_z IS NOT NULL
        ORDER BY last_visited DESC, system_address DESC
        """
    )

    sectors_map: Dict[Optional[str], Dict[str, Any]] = {}
    region_visited = 0
    region_external = 0
    region_scanned = 0
    region_total_bodies = 0

    for row in cur.fetchall():
        if _resolve_region_id(row["star_pos_x"], row["star_pos_z"]) != rid:
            continue
        sector = extract_sector_name(row["star_system"])  # None => Named / Catalog
        entry = sectors_map.get(sector)
        if entry is None:
            entry = {
                "sector_name": sector or "",
                "is_named_catalog": sector is None,
                "visited_systems": 0,
                "external_systems": 0,
                "total_visits": 0,
                "scanned_bodies": 0,
                "total_bodies": 0,
                "fss_complete_systems": 0,
                "elw_count": 0,
                "ww_count": 0,
                "last_visited": "",
                "sample_systems": [],
            }
            sectors_map[sector] = entry

        is_ext = int(row["is_external"] or 0)
        tot_b = int(row["total_bodies"] or 0)
        scn_b = int(row["scanned_bodies"] or 0)
        v_cnt = int(row["visit_count"] or 0)
        lv = row["last_visited"] or ""

        if is_ext:
            entry["external_systems"] += 1
            region_external += 1
            continue

        entry["visited_systems"] += 1
        entry["total_visits"] += v_cnt
        entry["scanned_bodies"] += scn_b
        entry["total_bodies"] += tot_b
        if tot_b > 0 and scn_b >= tot_b:
            entry["fss_complete_systems"] += 1
        entry["elw_count"] += 1 if row["has_elw"] else 0
        entry["ww_count"] += 1 if row["has_water_world"] else 0
        if lv > entry["last_visited"]:
            entry["last_visited"] = lv

        if len(entry["sample_systems"]) < 6:
            entry["sample_systems"].append({
                "system_address": row["system_address"],
                "star_system": row["star_system"] or "",
                "visit_count": v_cnt,
                "scanned_bodies": scn_b,
                "total_bodies": tot_b,
            })

        region_visited += 1
        region_scanned += scn_b
        region_total_bodies += tot_b

    sectors_list = [
        v for v in sectors_map.values() if v["visited_systems"] > 0 or v["external_systems"] > 0
    ]
    sectors_list.sort(
        key=lambda s: (s["visited_systems"], s["scanned_bodies"], s["total_visits"]),
        reverse=True,
    )

    return {
        "region": {
            "region_id": rid,
            "name_en": name_en,
            "name_ja": name_ja,
            "visited_systems": region_visited,
            "external_systems": region_external,
            "sector_count": sum(1 for s in sectors_list if not s["is_named_catalog"] and s["visited_systems"] > 0),
            "scanned_bodies": region_scanned,
            "total_bodies": region_total_bodies,
        },
        "sectors": sectors_list,
    }
