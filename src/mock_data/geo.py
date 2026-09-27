"""Land-polygon checks for synthetic Puerto Rico site coordinates.

Shape provenance: the three polygons below (main island, Vieques, Culebra)
are hand-digitized simplified approximations of each island's coastline —
12 to 22 vertices each, built from public-domain approximate longitude/
latitude landmarks. They are **not** survey-grade GIS data and must not be
used for anything beyond plausibility-checking synthetic site coordinates
in this demo. Tolerance: point-in-polygon membership is checked with a
``LAND_TOLERANCE_DEG`` (~0.01 degrees, ~1.1 km at this latitude) buffer, so a
point a few hundred meters off the simplified coastline still passes. A
bounding box alone would accept points in open ocean between Puerto Rico and
Vieques/Culebra, which this explicitly rejects.
"""

from __future__ import annotations

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

LAND_TOLERANCE_DEG = 0.01

# Main island of Puerto Rico — simplified coastline (lon, lat), clockwise.
_PR_MAIN_COORDS = [
    (-67.24, 18.47),
    (-66.93, 18.49),
    (-66.60, 18.47),
    (-66.24, 18.44),
    (-65.86, 18.38),
    (-65.63, 18.30),
    (-65.62, 18.16),
    (-65.72, 18.02),
    (-65.90, 17.94),
    (-66.15, 17.93),
    (-66.45, 17.95),
    (-66.75, 17.97),
    (-67.05, 17.98),
    (-67.20, 18.08),
    (-67.28, 18.25),
    (-67.24, 18.47),
]

# Vieques — simplified coastline.
_VIEQUES_COORDS = [
    (-65.55, 18.155),
    (-65.42, 18.165),
    (-65.31, 18.15),
    (-65.30, 18.11),
    (-65.42, 18.095),
    (-65.55, 18.10),
    (-65.55, 18.155),
]

# Culebra — simplified coastline.
_CULEBRA_COORDS = [
    (-65.335, 18.335),
    (-65.27, 18.34),
    (-65.23, 18.31),
    (-65.26, 18.28),
    (-65.32, 18.285),
    (-65.335, 18.335),
]

PR_MAIN_POLYGON = Polygon(_PR_MAIN_COORDS)
VIEQUES_POLYGON = Polygon(_VIEQUES_COORDS)
CULEBRA_POLYGON = Polygon(_CULEBRA_COORDS)

PUERTO_RICO_LAND = unary_union(
    [
        PR_MAIN_POLYGON.buffer(LAND_TOLERANCE_DEG),
        VIEQUES_POLYGON.buffer(LAND_TOLERANCE_DEG),
        CULEBRA_POLYGON.buffer(LAND_TOLERANCE_DEG),
    ]
)


def is_on_land(lon: float, lat: float) -> bool:
    """True if (lon, lat) falls within tolerance of the simplified coastline."""
    return PUERTO_RICO_LAND.contains(Point(lon, lat))


def sample_land_point(rng, polygon: Polygon, max_attempts: int = 500) -> tuple[float, float]:
    """Deterministic rejection-sample a point inside ``polygon`` using ``rng``.

    ``rng`` must be a ``numpy.random.Generator`` seeded per-entity upstream so
    repeated runs with the same seed reproduce identical coordinates.
    """
    minx, miny, maxx, maxy = polygon.bounds
    for _ in range(max_attempts):
        lon = rng.uniform(minx, maxx)
        lat = rng.uniform(miny, maxy)
        if polygon.contains(Point(lon, lat)):
            return round(lon, 6), round(lat, 6)
    raise RuntimeError("sample_land_point exceeded max_attempts; polygon too thin for its bbox")
