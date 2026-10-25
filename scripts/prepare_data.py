"""Heavy numerical + actual OSM preparation. Run in GitHub Actions/Colab, not the API."""
from pathlib import Path
import argparse,json,sys,tempfile,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from prepare_candidates import NumericGeoRisk,prepare
from prepare_osm import screen
from verify_data import verify

def main():
 p=argparse.ArgumentParser();p.add_argument('--spacing-m',type=int,default=240,choices=[120,240]);args=p.parse_args()
 geo=NumericGeoRisk(ROOT/'reference/georisk');terrain=geo.check_fixtures(ROOT/'reference/georisk/fixtures.json')
 csv_path,osm=screen(geo,ROOT/'.preparation-cache',spacing_m=args.spacing_m)
 with tempfile.TemporaryDirectory(prefix='candidate-prep-',dir=ROOT) as tmp:
  dest=Path(tmp);rows,meta=prepare(csv_path,geo,dest,screening_source=osm['source'],screening_date=osm['retrieved_at'])
  if not rows:raise ValueError('No real candidates passed current OSM/numeric checks. Existing data have not been overwritten.')
  meta['osm_screening']=osm;(dest/'manifest.json').write_text(json.dumps(meta,indent=2))
  status=verify(dest);report={'status':status,'numeric_fixture_checks':terrain,'osm_screening':osm,'exclusions':meta['exclusions'],'note':'Candidate locations are real numerical/access-screened preparation outputs, not observed lichen sites or permission to visit.'}
  (dest/'preparation-report.json').write_text(json.dumps(report,indent=2))
  data=ROOT/'data';data.mkdir(exist_ok=True)
  for name in ['candidates.json','manifest.json','preparation-report.json']:shutil.copyfile(dest/name,data/name)
 (ROOT/'BUILD_STATUS.json').write_text(json.dumps({'code_ready':True,**status},indent=2))
 print(json.dumps(status,indent=2))
if __name__=='__main__':main()
