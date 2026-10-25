"""Actual terrain fixtures verify numbers only; no biological observations created."""
import unittest,json,struct,csv,tempfile
from pathlib import Path
from prepare_candidates import NumericGeoRisk,prepare,inverse
ROOT=Path(__file__).resolve().parents[1]
class NumericTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.geo=NumericGeoRisk(ROOT/'reference/georisk')
 def test_all24_real_numeric_fixtures_and_full_cdf(self):
  r=self.geo.check_fixtures(ROOT/'reference/georisk/fixtures.json');self.assertEqual(r['numerical_terrain_fixtures_passed'],24);self.assertEqual(r['fixed_cdf_samples'],1473136)
 def test_outside_nodata_and_nearest_rounding(self):
  g=self.geo;m=g.manifest;self.assertIsNone(g.sample(0,0));f=json.loads((ROOT/'reference/georisk/fixtures.json').read_text())[9];x=m['first_sample_center_xy'][0]+20*f['column'];y=m['first_sample_center_xy'][1]-20*f['row']
  self.assertEqual(g.sample(*inverse(x+9.9,y))['georisk_column'],f['column'])
  for i,(v,) in enumerate(struct.iter_unpack('<H',g.data)):
   if v==65535:
    row,col=divmod(i,m['shape'][1]);lat,lon=inverse(m['first_sample_center_xy'][0]+20*col,m['first_sample_center_xy'][1]-20*row)
    if m['bounds_wgs84'][0]<=lon<=m['bounds_wgs84'][2] and m['bounds_wgs84'][1]<=lat<=m['bounds_wgs84'][3]:self.assertIsNone(g.sample(lat,lon));break
 def test_preparation_never_imports_palette_risk_or_unscreened_access(self):
  f=json.loads((ROOT/'reference/georisk/fixtures.json').read_text())[9];r=dict(candidate_id='SYNTHETIC-PREPARATION-ONLY',latitude=f['latitude'],longitude=f['longitude'],eligible_for_sampling=True,inside_building=False,inside_water_or_wetland=False,inside_industrial=False,explicitly_restricted=False,distance_to_road_m=50,distance_to_major_road_m=100,distance_to_railway_m=100,distance_to_crop_edge_m=200,site_type='park',access_status='field_verification_required',risk_score=999)
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);p=td/'synthetic-input.csv'
   def write(row):
    with p.open('w',newline='') as f:
     w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row)
   write(r);rows,meta=prepare(p,self.geo,td/'out',screening_source='SYNTHETIC TEST ONLY',screening_date='2026-10-24T00:00:00Z');self.assertEqual(rows[0]['georisk_raw'],f['raw_score']);self.assertNotIn('risk_score',rows[0]);self.assertIsNone(rows[0]['historical_change_score'])
   r.pop('inside_building');write(r);rows,_=prepare(p,self.geo,td/'out',screening_source='SYNTHETIC TEST ONLY',screening_date='2026-10-24T00:00:00Z');self.assertEqual(rows,[])
if __name__=='__main__':unittest.main()
