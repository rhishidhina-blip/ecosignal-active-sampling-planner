"""Deployment guard: source integrity and actual numeric samples, never display colors."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from eco_planner.engine import Config,validate_pool
from prepare_candidates import NumericGeoRisk

def verify(directory=None):
 data=Path(directory) if directory else ROOT/'data'
 for name in ['manifest.json','candidates.json']:
  if not (data/name).is_file():raise ValueError('Real candidate data missing. In GitHub, run Actions > Prepare real planner data > Run workflow, or copy the two real data files from your Colab Render ZIP into data/.')
 meta=json.loads((data/'manifest.json').read_text());payload=(data/'candidates.json').read_bytes();rows=json.loads(payload)
 if not isinstance(meta,dict) or meta.get('evidence_kind')!='real_candidate_preparation':raise ValueError('Only actual candidate preparation outputs can be deployed; no synthetic/example pools.')
 if hashlib.sha256(payload).hexdigest()!=meta.get('candidates_sha256'):raise ValueError('Candidate file checksum mismatch')
 cfg=Config(**json.loads((ROOT/'config.json').read_text()));validate_pool(rows,meta,cfg)
 if not rows:raise ValueError('No real candidates passed screening; do not deploy an empty pool.')
 geo=NumericGeoRisk(ROOT/'reference/georisk')
 if meta.get('bounds_wgs84')!=geo.manifest['bounds_wgs84'] or meta.get('georisk_cdf_sha256')!=geo.cdf_sha:raise ValueError('Wrong coverage or fixed full sampled-cohort CDF')
 for c in rows:
  sample=geo.sample(c['latitude'],c['longitude'])
  if sample is None or abs(sample['georisk_raw']-c.get('georisk_raw',-1))>1e-10 or abs(sample['georisk_percentile']-c['georisk_percentile'])>1e-6:raise ValueError('A candidate does not match the actual numerical grid/reference')
  if not isinstance(c.get('site_type'),str) or not c['site_type'].strip():raise ValueError('Candidate site type is missing')
 return {'ready_for_data_serving':True,'real_candidate_rows':len(rows),'candidates_sha256':meta['candidates_sha256'],'reference_version':meta['georisk_reference_version'],'reference_samples':geo.cdf['sample_count'],'observed_lichen_sites_bundled':0,'scientific_validation':'not_run'}
if __name__=='__main__':
 try:print(json.dumps(verify(),indent=2))
 except (ValueError,OSError,KeyError,TypeError) as exc:print('NOT READY:',str(exc),file=sys.stderr);sys.exit(1)
