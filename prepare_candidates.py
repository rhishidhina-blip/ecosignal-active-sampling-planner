"""Offline-only preparation: verified numeric terrain and actual access-screened candidates."""
from pathlib import Path
import csv, json, hashlib, math, struct, io
from collections import Counter
from datetime import datetime, timezone

REFERENCE='georisk-2024-native-features-20m-sampling-v1'
BINARY_SHA='cb1bd7e15d47cbbd9d2a4282108061ca17b5d1600c9e13b78c29934f47309ec7'
RAD=math.pi/180;A=6378137;f=1/298.257222101;E=math.sqrt(f*(2-f))
def t(p):return math.tan(math.pi/4-p/2)/((1-E*math.sin(p))/(1+E*math.sin(p)))**(E/2)
def m(p):return math.cos(p)/math.sqrt(1-E*E*math.sin(p)**2)
p1,p2=36.1666666666667*RAD,34.3333333333333*RAD
N=(math.log(m(p1))-math.log(m(p2)))/(math.log(t(p1))-math.log(t(p2)));F=m(p1)/(N*t(p1)**N);RHO0=A*F*t(33.75*RAD)**N
def project(lat,lon):
 rho=A*F*t(lat*RAD)**N;theta=N*(lon+79)*RAD
 return 609601.22+rho*math.sin(theta),RHO0-rho*math.cos(theta)
def inverse(x,y):
 dx=x-609601.22;dy=RHO0-y;rho=math.hypot(dx,dy);theta=math.atan2(dx,dy);tt=(rho/(A*F))**(1/N);p=math.pi/2-2*math.atan(tt)
 for _ in range(12):p=math.pi/2-2*math.atan(tt*((1-E*math.sin(p))/(1+E*math.sin(p)))**(E/2))
 return p/RAD,-79+theta/(N*RAD)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
class NumericGeoRisk:
 def __init__(self,directory):
  d=Path(directory);self.manifest=json.loads((d/'georisk-numeric-manifest.json').read_text());self.cdf=json.loads((d/'georisk-reference-cdf.json').read_text());self.data=(d/self.manifest['binary_file']).read_bytes()
  self.cdf_sha=digest(d/'georisk-reference-cdf.json');self.manifest_sha=digest(d/'georisk-numeric-manifest.json')
  if self.manifest['version']!=REFERENCE or self.manifest['binary_sha256']!=BINARY_SHA or hashlib.sha256(self.data).hexdigest()!=BINARY_SHA:raise ValueError('Wrong numerical terrain source/hash')
  if len(self.data)!=2*math.prod(self.manifest['shape']) or self.cdf['sample_count']!=1473136 or len(self.cdf['cdf_percent'])!=10001:raise ValueError('Wrong grid or fixed reference')
  if self.cdf['version']!=REFERENCE or self.cdf['score_divisor']!=10000:raise ValueError('Wrong fixed CDF version/divisor')
  self.validate_full_cdf()
 def validate_full_cdf(self):
  hist=[0]*10001
  for (v,) in struct.iter_unpack('<H',self.data):
   if v==65535:continue
   if v>10000:raise ValueError('Invalid uint16 terrain value')
   hist[v]+=1
  count=sum(hist)
  if count!=1473136:raise ValueError('Wrong cohort size')
  cumulative=0
  for v,n in enumerate(hist):
   cumulative+=n
   if abs(self.cdf['cdf_percent'][v]-100*cumulative/count)>1e-7:raise ValueError('CDF does not match full fixed sampled cohort')
 def sample(self,lat,lon):
  if not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)) or not math.isfinite(lat+lon):return None
  west,south,east,north=self.manifest['bounds_wgs84']
  if not(west<=lon<=east and south<=lat<=north):return None
  x,y=project(lat,lon);x0,y0=self.manifest['first_sample_center_xy'];step=self.manifest['sample_spacing_m']
  col=math.floor((x-x0)/step+.5);row=math.floor((y0-y)/step+.5);h,w=self.manifest['shape']
  if not(0<=row<h and 0<=col<w):return None
  dist=math.hypot(x-(x0+col*step),y-(y0-row*step))
  if dist>math.sqrt(2)*step/2+1e-6:return None
  v=struct.unpack_from('<H',self.data,2*(row*w+col))[0]
  if v==65535:return None
  return dict(georisk_raw=v/10000,georisk_percentile=self.cdf['cdf_percent'][v],georisk_row=row,georisk_column=col,sample_distance_m=dist,source_year=2024,sample_spacing_m=20)
 def check_fixtures(self,path):
  fixtures=json.loads(Path(path).read_text())
  for f in fixtures:
   q=self.sample(f['latitude'],f['longitude'])
   assert q is not None and q['georisk_row']==f['row'] and q['georisk_column']==f['column']
   assert q['georisk_raw']==f['raw_score'] and abs(q['georisk_percentile']-f['percentile'])<1e-8 and q['sample_distance_m']<.001
  return {'numerical_terrain_fixtures_passed':len(fixtures),'not_lichen_observations':True,'fixed_cdf_samples':self.cdf['sample_count'],'binary_sha256':BINARY_SHA}

def num(v):
 try:
  q=float(v)
  return q if math.isfinite(q) else None
 except (ValueError,TypeError):return None
def yes(v):return v is True or (isinstance(v,str) and v.strip().lower() in ('true','1','yes'))
def no(v):return v is False or (isinstance(v,str) and v.strip().lower() in ('false','0','no'))

def prepare(csv_path,georisk,output,*,screening_source,screening_date,historical_change_provenance=None,dataset_version=None):
 """Reject unscreened rows. Never trust old palette values or legacy lichen stress."""
 if not screening_source.strip():raise ValueError('Declare the real screening source')
 from eco_planner.engine import stamp
 stamp(screening_date)
 raw=Path(csv_path).read_bytes();source_sha=hashlib.sha256(raw).hexdigest();rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
 seen=set();out=[];excluded=Counter()
 for r in rows:
  cid=r.get('candidate_id','').strip()
  if not cid or cid in seen:raise ValueError('Candidate IDs must be nonblank and unique')
  seen.add(cid);lat=num(r.get('latitude'));lon=num(r.get('longitude'))
  if lat is None or lon is None:excluded['invalid_location']+=1;continue
  if not yes(r.get('eligible_for_sampling')):excluded['not_screened_eligible']+=1;continue
  flags=['inside_building','inside_water_or_wetland','inside_industrial','explicitly_restricted']
  if not all(no(r.get(k)) for k in flags):excluded['missing_or_failed_safety_flags']+=1;continue
  distances=[(num(r.get(k)),threshold) for k,threshold in [('distance_to_road_m',8),('distance_to_major_road_m',30),('distance_to_railway_m',8),('distance_to_crop_edge_m',75)]]
  if any(v is None or v<th for v,th in distances):excluded['missing_or_failed_distance_screen']+=1;continue
  kind=r.get('site_type','').strip();access=r.get('access_status','').strip()
  if not kind or access not in ('permission_required','field_verification_required','likely_public_verify_hours','public_access_verified'):excluded['unknown_or_excluded_access']+=1;continue
  if access=='public_access_verified' and not r.get('access_evidence','').strip():access='field_verification_required'
  g=georisk.sample(lat,lon)
  if g is None:excluded['outside_numeric_coverage_or_nodata']+=1;continue
  change=num(r.get('recent_change_score')) if historical_change_provenance else None
  if change is not None and not 0<=change<=1:raise ValueError('Historical change outside0..1')
  out.append(dict(candidate_id=cid,latitude=lat,longitude=lon,site_type=kind,access_status=access,
      safety_screened=True,eligible_for_sampling=True,screening_source=screening_source,screening_date=screening_date,
      historical_change_score=change,**g))
 meta=dict(schema='EcoSignal-planner-candidates-v3',dataset_version=dataset_version or 'candidates-'+source_sha[:12],
   evidence_kind='synthetic_test' if 'synthetic' in screening_source.lower() else 'real_candidate_preparation',source_file=Path(csv_path).name,source_sha256=source_sha,generated_at=datetime.now(timezone.utc).isoformat(),
   source_rows=len(rows),retained_rows=len(out),exclusions=dict(excluded),bounds_wgs84=georisk.manifest['bounds_wgs84'],
   georisk_reference_version=REFERENCE,georisk_binary_sha256=BINARY_SHA,georisk_cdf_sha256=georisk.cdf_sha,
   georisk_manifest_sha256=georisk.manifest_sha,georisk_model_sha256=georisk.manifest['model_sha256'],
   source_dem_sha256=georisk.manifest['source_dem_sha256'],sampling='nearest20m lattice point, no interpolation; fixed full sampled-cohort CDF, not full1m-pixel CDF',
   screening_source=screening_source,screening_date=screening_date,historical_change_provenance=historical_change_provenance,
   dropped_legacy_fields=['risk_score','uncertainty_score','sparsity_score','control_score','priority_score','terrain_diversity_score','lichen_stress'],
   warnings=['Original candidate pool may already exclude sites near old sample points. For unbiased new coverage, regenerate geometry without old observation-based pruning.','No chlorosis/nitrophyte/growth-form tolerance values were invented.','Access labels are not permission. Unknown or missing safety distances fail closed.'])
 dest=Path(output);dest.mkdir(parents=True,exist_ok=True);payload=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode();(dest/'candidates.json').write_bytes(payload);meta['candidates_sha256']=hashlib.sha256(payload).hexdigest();(dest/'manifest.json').write_text(json.dumps(meta,indent=2,allow_nan=False))
 return out,meta

def make_grid(georisk,spacing_m=120,max_candidates=50000):
 """Geometry from actual valid numeric lattice; no assumed observations or OSM access."""
 if spacing_m<60:raise ValueError('Use at least60m candidate spacing for a bounded export')
 step=max(1,round(spacing_m/20));h,w=georisk.manifest['shape'];x0,y0=georisk.manifest['first_sample_center_xy'];out=[]
 for row in range(0,h,step):
  for col in range(0,w,step):
   if min(row,h-1-row,col,w-1-col)*20<75:continue
   v=struct.unpack_from('<H',georisk.data,2*(row*w+col))[0]
   if v==65535:continue
   x=x0+col*20;y=y0-row*20;lat,lon=inverse(x,y)
   out.append(dict(candidate_id=f'GR24-R{row}-C{col}',latitude=lat,longitude=lon,x=x,y=y,row=row,col=col,terrain_type='unknown',distance_to_crop_edge_m=min(row,h-1-row,col,w-1-col)*20))
   if len(out)>max_candidates:raise ValueError('Too many candidates; increase grid spacing')
 return out
