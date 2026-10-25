"""Actual OSM screening with spatial indices; original classification/access rules retained."""
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib


def save_osm_evidence(features, path, chunk_size=500):
    """Stream full source features and SHA-256 with bounded conversion batches.

    GeoDataFrame.to_json() and iterfeatures() on the complete wide OSM frame
    materialize large object arrays. Call iterfeatures only on small slices.
    Never read the completed multi-hundred-MB evidence file back into memory.
    """
    import os
    import tempfile
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if chunk_size < 1:
        raise ValueError('Evidence chunk size must be positive')
    digest = hashlib.sha256()
    count = 0
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=target.parent, prefix=target.name+'.', suffix='.tmp', delete=False) as out:
            temporary = Path(out.name)

            def write(text):
                payload = text.encode('utf-8')
                out.write(payload)
                digest.update(payload)

            write('{"type":"FeatureCollection","features":[')
            for start in range(0, len(features), chunk_size):
                # OSM frames have many sparse tag columns: do not repeat every
                # absent tag as null for every one of the 455k source features.
                for feature in features.iloc[start:start+chunk_size].iterfeatures(na='drop'):
                    if count:
                        write(',')
                    write(json.dumps(feature, ensure_ascii=False, allow_nan=False, separators=(',', ':')))
                    count += 1
                if count % 10000 == 0 or count == len(features):
                    print(f'Stage: saved OSM evidence {count:,}/{len(features):,} features', flush=True)
            write(']}')
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {'sha256': digest.hexdigest(), 'feature_count': count, 'bytes': target.stat().st_size}


def indexed_within(points, features):
    """Exact within-union semantics, including shared polygon boundaries."""
    import numpy as np
    import pandas as pd
    result = np.zeros(len(points), dtype=bool)
    if features is not None and len(features):
        hits = features.sindex.query(points, predicate='within')
        if hits.size:
            result[hits[0]] = True
        # At a shared edge a point can be inside the union without being inside
        # either individual polygon. Resolve only these boundary cases locally.
        boundary_hits = features.sindex.query(points, predicate='intersects')
        if boundary_hits.size:
            for index in np.unique(boundary_hits[0]):
                if not result[index]:
                    local = boundary_hits[1][boundary_hits[0] == index]
                    result[index] = points.iloc[index].within(features.iloc[local].union_all())
    return pd.Series(result, index=points.index)


def indexed_distance(points, features):
    """Nearest exact geometry distance, without an expensive region-wide union."""
    import numpy as np
    import pandas as pd
    result = np.full(len(points), np.inf)
    if features is not None and len(features):
        pairs, distances = features.sindex.nearest(points, return_all=False, return_distance=True)
        result[pairs[0]] = distances
    return pd.Series(result, index=points.index)


def screen(georisk, output, spacing_m=120):
    import numpy as np
    import pandas as pd
    from prepare_candidates import make_grid
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    print(f'Stage: building numerical GeoRisk candidate grid, spacing {spacing_m}m', flush=True)
    rows = make_grid(georisk, spacing_m)
    candidates = pd.DataFrame(rows)
    print(f'Stage: {len(rows):,} actual numerical grid candidates; starting OSM screening', flush=True)
    ns = {'crop_bounds_wgs84': georisk.manifest['bounds_wgs84'],
          'profile_2022': {'crs': 'EPSG:32119'}, 'np': np, 'pd': pd,
          'cache_root': out, 'indexed_within': indexed_within, 'indexed_distance': indexed_distance}
    exec(SCREENING_SOURCE, ns)
    if ns['road_geometry'] is None:
        raise ValueError('No roads returned; cannot verify offset screening')
    gpd = ns['gpd']
    points = gpd.GeoDataFrame(candidates, geometry=gpd.points_from_xy(candidates.x, candidates.y), crs='EPSG:32119')
    print(f'Stage: screening {len(points):,} candidates with indexed exact geometry predicates', flush=True)
    # Chunking bounds predicate intermediates and gives real progress, not a fake percentage.
    chunks = []
    for start in range(0, len(points), 1000):
        chunks.append(ns['point_flags'](points.iloc[start:start+1000]))
        print(f'Stage: screened {min(start+1000, len(points)):,}/{len(points):,} candidates', flush=True)
    if not chunks:
        raise ValueError('No valid numerical candidate locations in study bounds')
    flagged = pd.concat(chunks)
    csv_path = out / 'planner_candidates.csv'
    flagged.drop(columns='geometry').to_csv(csv_path, index=False)
    print('Stage: saving OSM source evidence and checksums', flush=True)
    osm_path = out / 'osm_features.geojson'
    evidence = save_osm_evidence(ns['osm_features'], osm_path)
    meta = {'source': 'OpenStreetMap via original v2 OSMnx2.1 screening, spatial-index adaptation v1, generated without lichen-based pruning',
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'features': len(ns['osm_features']),
            'geometry_candidates': len(rows), 'screened_eligible_before_numeric_checks': int(flagged.eligible_for_sampling.sum()),
            'osm_geojson_sha256': evidence['sha256'],
            'osm_geojson_bytes': evidence['bytes'],
            'osm_geojson_feature_count': evidence['feature_count'],
            'osm_evidence_serialization': 'streamed GeoJSON; absent/null tags omitted; nonmissing source properties and geometry retained',
            'terrain_type': 'unknown: no elevation inferred from risk scores', 'spacing_m': spacing_m,
            'minimum_road_offset_m': 8, 'major_road_exclusion_m': 30, 'minimum_railway_offset_m': 8,
            'source_age': 'current OSM retrieval, not guaranteed complete or legal access',
            'method_change': 'spatial indices replace region-wide union_all; local boundary unions retain within-union semantics'}
    (out / 'osm_screening_manifest.json').write_text(json.dumps(meta, indent=2))
    return csv_path, meta

SCREENING_SOURCE = '# ACTIVE SAMPLING PLANNER — VALIDATION STEP 1\n# Paste this as a NEW CELL immediately after Section 4\'s candidate-building cell.\n\nimport importlib.util\nimport subprocess\nimport sys\n\nif importlib.util.find_spec("osmnx") is None:\n    subprocess.check_call([\n        sys.executable, "-m", "pip", "install", "-q",\n        "osmnx==2.1.0"\n    ])\n\nimport geopandas as gpd\nimport osmnx as ox\nfrom shapely.geometry import Point\n\nox.settings.use_cache = True\nox.settings.requests_timeout = 120\nox.settings.log_console = True\nox.settings.log_file = True\nox.settings.cache_folder = str(cache_root / "overpass")\nox.settings.logs_folder = str(cache_root / "logs")\nprint("Stage: retrieving current OSM features for complete study bounds (requests timeout 120s; server rate limiting respected)", flush=True)\n\n# Safety/access distances. These are conservative field-planning defaults,\n# not legal determinations of where sampling is permitted.\nROADSIDE_MAX_DISTANCE_M = 40.0\nMINIMUM_ROAD_OFFSET_M = 8.0\nMAJOR_ROAD_EXCLUSION_M = 30.0\n\n# OSMnx 2.1 expects (left, bottom, right, top) in EPSG:4326.\nosm_bbox = tuple(float(v) for v in crop_bounds_wgs84)\n\n# The query is a union: it retrieves every feature matching at least one tag.\nosm_tags = {\n    "highway": True,\n    "building": True,\n    "landuse": [\n        "forest", "recreation_ground", "grass", "meadow", "education",\n        "residential", "industrial", "commercial", "retail"\n    ],\n    "leisure": [\n        "park", "nature_reserve", "garden", "recreation_ground",\n        "playground", "sports_centre", "pitch"\n    ],\n    "amenity": ["school", "kindergarten", "college", "university"],\n    "natural": ["wood", "water", "wetland"],\n    "waterway": ["riverbank", "dock"],\n    "railway": True,\n}\n\ntry:\n    osm_features = ox.features.features_from_bbox(osm_bbox, osm_tags)\nexcept Exception as exc:\n    raise RuntimeError(\n        "OpenStreetMap retrieval failed. Wait 1–2 minutes and rerun this cell. "\n        "If it fails again, confirm that the Colab runtime has internet access."\n    ) from exc\n\nif osm_features.empty:\n    raise RuntimeError("OpenStreetMap returned no features for the EcoSignal study bounds.")\n\nprint(f"Stage: retrieved {len(osm_features):,} OSM features; projecting", flush=True)\nosm_projected = osm_features.to_crs(profile_2022["crs"]).copy()\nosm_projected = osm_projected[osm_projected.geometry.notna() & ~osm_projected.geometry.is_empty]\n\n\ndef tag_matches(frame, column, allowed_values=None):\n    """Safely match scalar or list-valued OSM tags."""\n    if column not in frame.columns:\n        return pd.Series(False, index=frame.index)\n\n    allowed = None if allowed_values is None else {str(v).lower() for v in allowed_values}\n\n    def match(value):\n        if value is None or (isinstance(value, float) and np.isnan(value)):\n            return False\n        values = value if isinstance(value, (list, tuple, set, np.ndarray)) else [value]\n        values = {str(v).lower() for v in values}\n        return bool(values) if allowed is None else bool(values & allowed)\n\n    return frame[column].apply(match)\n\n\ndef polygon_union(mask):\n    polygon_types = osm_projected.geometry.geom_type.isin(["Polygon", "MultiPolygon"])\n    geometry = osm_projected.loc[mask & polygon_types, "geometry"]\n    return None if geometry.empty else geometry.reset_index(drop=True)\n\n\ndef linear_union(mask):\n    line_types = osm_projected.geometry.geom_type.isin(["LineString", "MultiLineString"])\n    geometry = osm_projected.loc[mask & line_types, "geometry"]\n    return None if geometry.empty else geometry.reset_index(drop=True)\n\n\nprint("Stage: indexing OSM land-use and exclusion geometries (no global unions)", flush=True)\n# Build real land-use and exclusion geometries.\nroad_mask = tag_matches(osm_projected, "highway")\nmajor_road_mask = tag_matches(\n    osm_projected,\n    "highway",\n    ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link"]\n)\nforest_mask = (\n    tag_matches(osm_projected, "landuse", ["forest"]) |\n    tag_matches(osm_projected, "natural", ["wood"])\n)\npark_mask = (\n    tag_matches(osm_projected, "leisure", ["park", "nature_reserve", "garden", "recreation_ground"]) |\n    tag_matches(osm_projected, "landuse", ["recreation_ground"])\n)\nschool_mask = (\n    tag_matches(osm_projected, "amenity", ["school", "kindergarten", "college", "university"]) |\n    tag_matches(osm_projected, "landuse", ["education"])\n)\nbuilding_mask = tag_matches(osm_projected, "building")\nwater_mask = (\n    tag_matches(osm_projected, "natural", ["water", "wetland"]) |\n    tag_matches(osm_projected, "waterway", ["riverbank", "dock"])\n)\nindustrial_mask = tag_matches(osm_projected, "landuse", ["industrial"])\nrailway_mask = tag_matches(osm_projected, "railway")\nrestricted_mask = (\n    tag_matches(osm_projected, "access", ["no", "private"]) |\n    tag_matches(osm_projected, "foot", ["no", "private"])\n)\n\nroad_geometry = linear_union(road_mask)\nmajor_road_geometry = linear_union(major_road_mask)\nforest_geometry = polygon_union(forest_mask)\npark_geometry = polygon_union(park_mask)\nschool_geometry = polygon_union(school_mask)\nbuilding_geometry = polygon_union(building_mask)\nwater_geometry = polygon_union(water_mask)\nindustrial_geometry = polygon_union(industrial_mask)\nrestricted_geometry = polygon_union(restricted_mask)\nrailway_geometry = linear_union(railway_mask)\n\n\ndef point_flags(points_gdf):\n    """Add real OSM land-use, road-distance, and access flags to point features."""\n    out = points_gdf.copy()\n\n    def within(geometry):\n        return indexed_within(out.geometry, geometry)\n\n    def distance(geometry):\n        return indexed_distance(out.geometry, geometry)\n\n    out["inside_forest"] = within(forest_geometry)\n    out["inside_park"] = within(park_geometry)\n    out["inside_school"] = within(school_geometry)\n    out["inside_building"] = within(building_geometry)\n    out["inside_water_or_wetland"] = within(water_geometry)\n    out["inside_industrial"] = within(industrial_geometry)\n    out["explicitly_restricted"] = within(restricted_geometry)\n    out["distance_to_road_m"] = distance(road_geometry)\n    out["distance_to_major_road_m"] = distance(major_road_geometry)\n    out["distance_to_railway_m"] = distance(railway_geometry)\n\n    # Precedence prevents a school or park near a road from being mislabeled roadside.\n    out["site_type"] = np.select(\n        [\n            out.inside_school,\n            out.inside_park,\n            out.inside_forest,\n            out.distance_to_road_m.between(MINIMUM_ROAD_OFFSET_M, ROADSIDE_MAX_DISTANCE_M),\n            out.terrain_type.eq("slope"),\n            out.terrain_type.eq("lowland"),\n            out.terrain_type.eq("ridge"),\n        ],\n        ["school", "park", "forest", "roadside", "slope", "lowland", "ridge"],\n        default="other",\n    )\n\n    # OSM absence is not evidence of public access.\n    out["access_status"] = np.select(\n        [\n            out.explicitly_restricted,\n            out.inside_school,\n            out.inside_park,\n        ],\n        ["excluded_private_or_no_access", "permission_required", "likely_public_verify_hours"],\n        default="field_verification_required",\n    )\n\n    out["exclusion_reason"] = np.select(\n        [\n            out.inside_building,\n            out.inside_water_or_wetland,\n            out.inside_industrial,\n            out.explicitly_restricted,\n            out.distance_to_major_road_m < MAJOR_ROAD_EXCLUSION_M,\n            out.distance_to_road_m < MINIMUM_ROAD_OFFSET_M,\n            out.distance_to_railway_m < MINIMUM_ROAD_OFFSET_M,\n        ],\n        [\n            "building_footprint",\n            "water_or_wetland",\n            "industrial_land",\n            "explicit_private_or_no_access",\n            "too_close_to_major_road",\n            "too_close_to_road_centerline",\n            "too_close_to_railway",\n        ],\n        default="",\n    )\n    out["eligible_for_sampling"] = out.exclusion_reason.eq("")\n    return out\n\n\n'
