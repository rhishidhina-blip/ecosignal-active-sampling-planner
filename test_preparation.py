"""Synthetic software regressions only; no field observations or network requests."""
from pathlib import Path
import contextlib
import io
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_osm import indexed_within, indexed_distance, SCREENING_SOURCE
from run_preparation import supervise


class PreparationTests(unittest.TestCase):
    def geometries(self):
        import geopandas as gpd
        from shapely.geometry import Point, box
        polygons = gpd.GeoSeries([box(0, 0, 2, 2), box(2, 0, 4, 2)], crs='EPSG:32119')
        points = gpd.GeoSeries([Point(1, 1), Point(2, 1), Point(4, 1), Point(5, 1), Point(2, 0)],
                               index=[10, 20, 30, 40, 50], crs=polygons.crs)
        return points, polygons

    def test_within_matches_union_including_shared_and_outer_boundaries(self):
        points, polygons = self.geometries()
        self.assertEqual(indexed_within(points, polygons).tolist(), points.within(polygons.union_all()).tolist())
        self.assertEqual(indexed_within(points, polygons).index.tolist(), points.index.tolist())

    def test_distance_matches_original_union(self):
        import numpy as np
        points, polygons = self.geometries()
        np.testing.assert_allclose(indexed_distance(points, polygons), points.distance(polygons.union_all()))

    def test_missing_geometries_remain_unknown_not_safe_distances(self):
        import numpy as np
        points, _ = self.geometries()
        self.assertFalse(indexed_within(points, None).any())
        self.assertTrue(np.isinf(indexed_distance(points, None)).all())

    def test_road_distance_parity(self):
        import geopandas as gpd
        import numpy as np
        from shapely.geometry import LineString
        points, _ = self.geometries()
        roads = gpd.GeoSeries([LineString([(0, -1), (0, 5)]), LineString([(10, 0), (10, 8)])], crs=points.crs)
        np.testing.assert_allclose(indexed_distance(points, roads), points.distance(roads.union_all()))

    def test_random_polygon_parity(self):
        import geopandas as gpd
        import numpy as np
        from shapely.geometry import Point, box
        rng = np.random.default_rng(17)
        polygons = gpd.GeoSeries([box(x, y, x+3, y+3) for x, y in rng.uniform(0, 10, (30, 2))], crs='EPSG:32119')
        points = gpd.GeoSeries([Point(x, y) for x, y in rng.uniform(-1, 15, (200, 2))], crs=polygons.crs)
        union = polygons.union_all()
        self.assertEqual(indexed_within(points, polygons).tolist(), points.within(union).tolist())
        np.testing.assert_allclose(indexed_distance(points, polygons), points.distance(union))

    def test_full_access_screening_matches_original_union_method(self):
        import geopandas as gpd
        import numpy as np
        import pandas as pd
        from shapely.geometry import Point, LineString, box
        from unittest.mock import patch
        geometries = [LineString([(0, 0), (200, 0)]), LineString([(0, 100), (200, 100)]),
                      box(20, 20, 60, 60), box(60, 20, 100, 60), box(110, 20, 140, 60),
                      box(145, 20, 170, 60), box(20, 110, 70, 150), box(75, 110, 100, 150)]
        features = gpd.GeoDataFrame({'highway': ['residential', 'primary']+[None]*6,
                                    'building': [None, None, 'yes', 'yes']+[None]*4,
                                    'amenity': [None]*4+['school']+[None]*3,
                                    'leisure': [None]*5+['park']+[None]*2,
                                    'natural': [None]*6+['water', None],
                                    'access': [None]*7+['private']}, geometry=geometries, crs='EPSG:32119')
        points = gpd.GeoDataFrame({'terrain_type': ['unknown']*12},
                                 geometry=[Point(x,y) for x,y in [(40,40),(60,40),(80,40),(120,40),
                                            (155,40),(30,120),(80,120),(180,40),(20,4),(30,95),(60,20),(0,200)]], crs=features.crs)
        # Baseline uses the same original rules with the old region-wide unions.
        baseline = SCREENING_SOURCE.replace('geometry.reset_index(drop=True)', 'geometry.union_all()')
        baseline = baseline.replace('return indexed_within(out.geometry, geometry)',
                                    'return pd.Series(False,index=out.index) if geometry is None else out.geometry.within(geometry)')
        baseline = baseline.replace('return indexed_distance(out.geometry, geometry)',
                                    'return pd.Series(np.inf,index=out.index) if geometry is None else out.geometry.distance(geometry)')
        with tempfile.TemporaryDirectory() as d, patch('osmnx.features.features_from_bbox', return_value=features), contextlib.redirect_stdout(io.StringIO()):
            base_ns = {'crop_bounds_wgs84': [0,0,1,1], 'profile_2022': {'crs': features.crs},
                       'np': np, 'pd': pd, 'cache_root': Path(d),
                       'indexed_within': indexed_within, 'indexed_distance': indexed_distance}
            old, new = dict(base_ns), dict(base_ns)
            exec(baseline, old)
            exec(SCREENING_SOURCE, new)
            pd.testing.assert_frame_equal(old['point_flags'](points), new['point_flags'](points))

    def test_success_logs_output_and_status(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()) as output:
            code = supervise([sys.executable, '-u', '-c', 'print("synthetic child result")'], log_dir=d)
            self.assertEqual(code, 0)
            self.assertIn('synthetic child result', output.getvalue())
            self.assertEqual(json.loads((Path(d)/'execution-status.json').read_text())['status'], 'success')

    def test_failure_never_becomes_success(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(supervise([sys.executable, '-c', 'raise RuntimeError("test failure")'], log_dir=d), 1)
            self.assertIn('test failure', (Path(d)/'preparation.log').read_text())
            self.assertEqual(json.loads((Path(d)/'execution-status.json').read_text())['status'], 'failed')

    def test_deadline_terminates_child_and_prints_heartbeat(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()) as output:
            code = supervise([sys.executable, '-c', 'import time; time.sleep(20)'],
                             deadline_seconds=.6, heartbeat_seconds=.2, log_dir=d)
            self.assertEqual(code, 124)
            self.assertIn('[heartbeat]', output.getvalue())
            self.assertEqual(json.loads((Path(d)/'execution-status.json').read_text())['status'], 'deadline_exceeded')


if __name__ == '__main__':
    unittest.main()
