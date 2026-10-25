"""Versioned, stateless candidate ranking. No image models or raster loads at request time."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from collections import Counter, defaultdict
import hashlib, json, math, re
import numpy as np

VERSION = 'EcoSignal-Adaptive-Planner-v3.0.0'
ORIGINAL_WEIGHTS = dict(terrain=.28, follow_up=.24, coverage_gap=.18, historical_change=.15, control=.10, diversity=.05)
# Explicit profile, never selected implicitly because a row is missing a value.
CURRENT_WEIGHTS = dict(terrain=.28/.75, follow_up=.24/.75, coverage_gap=.18/.75, historical_change=0., control=0., diversity=.05/.75)
LIMITATIONS = [
 'Priority is a provisional field-planning heuristic, not environmental concern, pollution, probability or calibrated model uncertainty.',
 'v3 retains spatial selection/access caps but retires the old chlorosis/nitrophyte/growth-form stress surface and legacy mixed risk.',
 'GeoRisk is a fixed 2024 numerical sampled-cohort susceptibility percentile, not future risk, erosion probability or depth.',
 'The current-compatible profile explicitly disables historical change and controls and preserves the relative weights of the remaining v2 terms. This is a versioned method change, not row-wise renormalization.',
 'Follow-up uses explicit rejected/review records; spatial sparsity uses accepted confirmed sites. Distance is not counted again as calibrated model uncertainty.',
 'Site-type diversity uses supplied site types, or an explicitly labelled nearest-candidate match within 200m. This does not verify land ownership or habitat.',
 'OSM screening is not legal permission, exhaustive hazard detection or confirmation of public access. Verify conditions and permission before visiting.',
 'No observations means candidate-only planning, not zero concern. Missing quality/confidence is not imputed.',
 'Software adaptation tests are synthetic and separate from observed data; no independent scientific validation is claimed.'
]
@dataclass(frozen=True)
class Config:
    method_version: str = VERSION
    profile: str = 'current_georisk_review_v1'
    recommendations: int = 10
    minimum_spacing_m: float = 120.
    exclude_near_accepted_m: float = 30.
    distance_cap_m: float = 750.
    review_radius_m: float = 150.
    site_join_tolerance_m: float = 25.
    maximum_age_days: float = 30.
    stratum_match_m: float = 200.
    max_school: int = 4
    max_roadside: int = 3
    max_other_type: int = 3
    max_permission: int = 4
    include_permission_required: bool = False
    def validate(self):
        if self.method_version != VERSION or self.profile not in ('current_georisk_review_v1','historical_change_complete_v1'):
            raise ValueError('Unsupported method/profile')
        if not isinstance(self.include_permission_required,bool): raise ValueError('Explicit permission policy required')
        for k in ('minimum_spacing_m','exclude_near_accepted_m','distance_cap_m','review_radius_m','site_join_tolerance_m','maximum_age_days','stratum_match_m'):
            if not finite(getattr(self,k)) or getattr(self,k)<=0:raise ValueError('Invalid '+k)
        for k in ('recommendations','max_school','max_roadside','max_other_type','max_permission'):
            if type(getattr(self,k)) is not int or getattr(self,k)<1:raise ValueError('Invalid '+k)
        if self.recommendations>50:raise ValueError('At most 50 recommendations')
        return self
    @property
    def weights(self): return dict(CURRENT_WEIGHTS if self.profile=='current_georisk_review_v1' else ORIGINAL_WEIGHTS)

def finite(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def point(lat,lon):return finite(lat) and finite(lon) and -90<=lat<=90 and -180<=lon<=180
def stamp(t):
    if not isinstance(t,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})',t):raise ValueError('Timestamp needs calendar date and time zone')
    d=datetime.fromisoformat(t.replace('Z','+00:00'))
    if d.utcoffset() is None or abs(d.utcoffset().total_seconds())>14*3600:raise ValueError('Invalid timezone')
    return d.astimezone(timezone.utc)
def distance(a,b):
    la,lo,lb,lob=map(math.radians,(a[0],a[1],b[0],b[1]));v=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lob-lo)/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(max(0,v))))
def sha_object(obj):
    def clean(x):
        if isinstance(x,float) and not math.isfinite(x):return {'invalid_numeric_metadata':str(x)}
        if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
        if isinstance(x,(list,tuple)):return [clean(v) for v in x]
        return x
    return hashlib.sha256(json.dumps(clean(obj),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def synthetic(row):
    return row.get('illustrative') is True or row.get('evidence_kind') in ('synthetic','example','fixture','demonstration') or bool(re.search(r'illustrative|synthetic|demonstration|example',str(row.get('source','')),re.I)) or bool(re.match(r'^(TEST|SYNTHETIC|DEMO)(?:-|_|$)',str(row.get('site_id','')),re.I))

def flatten_observation(row):
    """Accept production-native companion exports, device records, or the documented flat API shape."""
    if not isinstance(row,dict):return {}
    source=row.get('source','')
    x=row.get('input') if isinstance(row.get('input'),dict) else row.get('screening') if isinstance(row.get('screening'),dict) else None
    if x is None:return dict(row)
    l=x.get('lichen') or {}; loc=x.get('location') or {}; raw=row.get('raw_model_output') or {}; c=raw.get('coverage') or {}
    return dict(observation_id=row.get('observation_id') or row.get('id'),site_id=x.get('site_id'),site_confirmed=x.get('site_confirmed'),
       latitude=loc.get('lat'),longitude=loc.get('lon'),captured_at=x.get('captured_at'),observed_at=l.get('observed_at'),
       source=l.get('source') or source,model_version=l.get('version') or c.get('version') or row.get('model_version'),
       coverage_status=c.get('status') or ('available' if l.get('coverage_percent') is not None else 'unavailable'),
       coverage_percent=l.get('coverage_percent'),coverage_confirmed=l.get('confirmed'),coverage_confidence=l.get('coverage_confidence'),
       requires_review=bool(row.get('correction')) or c.get('status') in ('rejected_low_confidence','failed','unavailable'),
       site_type=row.get('site_type'),illustrative=x.get('illustrative') is True or row.get('illustrative') is True,evidence_kind=row.get('evidence_kind'))

def observations_from_document(doc):
    if isinstance(doc,list):return [flatten_observation(r) for r in doc]
    if not isinstance(doc,dict):raise ValueError('Observation JSON must be an object or list')
    if isinstance(doc.get('observations'),list):return [flatten_observation(r) for r in doc['observations']]
    raise ValueError('Use the production JSON export (observations), not a legacy lat/lon-only table')

def eligible_observations(observations, bounds, now, cfg, allow_synthetic=False):
    seen=set(); checked=[];issues=[]
    west,south,east,north=bounds
    for raw in observations:
        r=flatten_observation(raw); oid=r.get('observation_id');sid=r.get('site_id');oid=oid.strip() if isinstance(oid,str) else None;sid=sid.strip() if isinstance(sid,str) else None;reasons=[]
        if not isinstance(oid,str) or not oid.strip():reasons.append('nonblank observation_id required')
        if not isinstance(sid,str) or not sid.strip():reasons.append('nonblank site_id required')
        if r.get('site_confirmed') is not True:reasons.append('explicit site confirmation required')
        if not point(r.get('latitude'),r.get('longitude')):reasons.append('valid coordinates required')
        elif not(west<=r['longitude']<=east and south<=r['latitude']<=north):reasons.append('outside planning coverage')
        if synthetic(r) and not allow_synthetic:reasons.append('test/example input excluded')
        if not isinstance(r.get('source'),str) or not r['source'].strip() or not isinstance(r.get('model_version'),str) or not r['model_version'].strip():reasons.append('source and model version required')
        try:
            captured=stamp(r.get('captured_at')); age=(now-captured).total_seconds()
            if age<0 or age>cfg.maximum_age_days*86400:reasons.append('future or stale capture')
        except (ValueError,TypeError):captured=None;reasons.append('actual capture timestamp required')
        if oid and oid in seen:reasons.append('duplicate observation_id')
        if oid:seen.add(oid)
        q=r.get('coverage_confidence')
        if q is not None and (not finite(q) or not 0<=q<=1):reasons.append('invalid confidence metadata')
        if reasons:issues.append({'observation_id':oid,'site_id':sid,'reasons':reasons});continue
        r={**r,'observation_id':oid.strip(),'site_id':sid.strip(),'capture':captured}
        r['accepted']=r.get('coverage_status')=='available' and r.get('coverage_confirmed') is True and finite(r.get('coverage_percent')) and 0<=r['coverage_percent']<=100
        if r['accepted']:
            try:
                if abs((stamp(r.get('observed_at'))-captured).total_seconds())>3600:r['accepted']=False
            except (ValueError,TypeError):r['accepted']=False
        r['review']=r.get('requires_review') is True or r.get('coverage_status') in ('rejected_low_confidence','failed','unavailable') or not r['accepted']
        checked.append(r)
    # Duplicate IDs invalidate every copy, not merely the last occurrence.
    duplicate_ids={x['observation_id'] for x in issues if 'duplicate observation_id' in x['reasons']}
    checked=[r for r in checked if r['observation_id'] not in duplicate_ids]
    groups=defaultdict(list)
    for r in checked:groups[r['site_id']].append(r)
    accepted=[];reviews=[]
    for sid,rows in groups.items():
        if distance((min(r['latitude'] for r in rows),min(r['longitude'] for r in rows)),(max(r['latitude'] for r in rows),max(r['longitude'] for r in rows)))>cfg.site_join_tolerance_m:
            issues.append({'site_id':sid,'reasons':['same site ID has conflicting locations; no automatic join']});continue
        rows.sort(key=lambda r:(r['capture'],r['observation_id']))
        valid=[r for r in rows if r['accepted']]
        if valid:accepted.append(valid[-1])
        if rows[-1]['review']:reviews.append(rows[-1])
    return accepted,reviews,issues

def _nearest(candidates,sites):
    """Bounded vector batches; avoids a full candidate-by-observation distance matrix."""
    if not sites:return np.full(len(candidates),np.inf),np.full(len(candidates),-1,dtype=int)
    a=np.radians(np.array([[c['latitude'],c['longitude']] for c in candidates]));b=np.radians(np.array([[s['latitude'],s['longitude']] for s in sites]));out=[];ids=[]
    for start in range(0,len(a),256):
        x=a[start:start+256];v=np.sin((x[:,0,None]-b[:,0])/2)**2+np.cos(x[:,0,None])*np.cos(b[:,0])*np.sin((x[:,1,None]-b[:,1])/2)**2
        d=6371000*2*np.arcsin(np.sqrt(np.clip(v,0,1)));i=np.argmin(d,axis=1);out.extend(d[np.arange(len(i)),i]);ids.extend(i)
    return np.array(out),np.array(ids)

def now_year():return datetime.now(timezone.utc).year

def validate_pool(candidates,metadata,cfg):
    cfg.validate()
    if not isinstance(candidates,list) or len(candidates)>50000:raise ValueError('Candidate list missing or exceeds 50000')
    if metadata.get('schema')!='EcoSignal-planner-candidates-v3' or not metadata.get('source_sha256') or not re.fullmatch('[a-f0-9]{64}',metadata['source_sha256']):raise ValueError('Candidate source provenance required')
    if metadata.get('georisk_reference_version')!='georisk-2024-native-features-20m-sampling-v1' or metadata.get('georisk_binary_sha256')!='cb1bd7e15d47cbbd9d2a4282108061ca17b5d1600c9e13b78c29934f47309ec7':raise ValueError('Wrong numeric terrain reference')
    if not isinstance(metadata.get('bounds_wgs84'),list) or len(metadata['bounds_wgs84'])!=4:raise ValueError('Planning bounds required')
    w,s,e,n=metadata['bounds_wgs84']
    if not all(finite(v) for v in [w,s,e,n]) or not(-180<=w<e<=180 and -90<=s<n<=90):raise ValueError('Invalid planning bounds')
    if cfg.profile=='historical_change_complete_v1':
        provenance=metadata.get('historical_change_provenance')
        if not isinstance(provenance,dict) or provenance.get('kind')!='observed_dem_difference' or not re.fullmatch('[a-f0-9]{64}',str(provenance.get('source_sha256',''))) or not isinstance(provenance.get('normalization'),str) or not provenance['normalization'].strip():raise ValueError('Historical change needs observed DEM source hash and normalization')
        period=provenance.get('period_years')
        if not isinstance(period,list) or len(period)!=2 or any(type(v) is not int for v in period) or not 1900<=period[0]<period[1]<=now_year():raise ValueError('Observed historical period required; future projections excluded')
    ids=set()
    for c in candidates:
        if not isinstance(c.get('candidate_id'),str) or not c['candidate_id'].strip() or c['candidate_id'] in ids:raise ValueError('Candidate IDs must be nonblank and unique')
        ids.add(c['candidate_id'])
        if not point(c.get('latitude'),c.get('longitude')) or not(w<=c['longitude']<=e and s<=c['latitude']<=n):raise ValueError('Candidate outside source coverage')
        if not finite(c.get('georisk_percentile')) or not 0<=c['georisk_percentile']<=100:raise ValueError('Numeric terrain percentile required')
        if c.get('safety_screened') is not True or c.get('eligible_for_sampling') is not True:raise ValueError('Only screened candidate rows may enter this pool')
        if not c.get('site_type') or not c.get('access_status') or not c.get('screening_source'):raise ValueError('Site type, access status and screening provenance required')
        if cfg.profile=='historical_change_complete_v1' and (not finite(c.get('historical_change_score')) or not 0<=c['historical_change_score']<=1 or not metadata.get('historical_change_provenance')):raise ValueError('Complete historical-change profile needs attributed change values for every candidate')
    return True

def rank_candidates(candidates,observations,metadata,config=None,now=None,site_types=None,allow_synthetic=False):
    cfg=(config or Config()).validate();validate_pool(candidates,metadata,cfg)
    now=now or datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None:raise ValueError('Timezone-aware as-of required')
    if len(observations)>5000:raise ValueError('At most 5000 observation records per request')
    accepted,reviews,issues=eligible_observations(observations,metadata['bounds_wgs84'],now,cfg,allow_synthetic)
    pool=[dict(c) for c in candidates if not str(c['access_status']).startswith('excluded') and (cfg.include_permission_required or c['access_status']!='permission_required')]
    dacc,_=_nearest(pool,accepted);dreview,_=_nearest(pool,reviews)
    # Site-type inference is used only for coverage diversity and reported as such.
    counts=Counter()
    if pool and accepted:
        ds,ix=_nearest(accepted,pool)
        for i,(d,j) in enumerate(zip(ds,ix)):
            explicit=accepted[i].get('site_type')
            if explicit:counts[explicit]+=1
            elif d<=cfg.stratum_match_m:counts[pool[int(j)]['site_type']]+=1
    denom=sum(counts.values());weights=cfg.weights;scored=[];skips=Counter()
    for i,c in enumerate(pool):
        if dacc[i]<cfg.exclude_near_accepted_m:skips['near_accepted_site']+=1;continue
        if site_types and c['site_type'] not in site_types:continue
        terrain=c['georisk_percentile']/100
        gap=min(1,float(dacc[i])/cfg.distance_cap_m)
        follow=max(0,1-float(dreview[i])/cfg.review_radius_m)
        diversity=1-counts[c['site_type']]/denom if denom else 1.
        change=c.get('historical_change_score')
        control=max(0,(.30-terrain)/.30)*gap*(1-change) if change is not None and weights['control']>0 else None
        strict_control=bool(control is not None and terrain<=.30 and change<=.35 and control>=.25)
        terms=dict(terrain=terrain,follow_up=follow,coverage_gap=gap,historical_change=change if weights['historical_change']>0 else None,control=control,diversity=diversity)
        parts={k:100*weights[k]*terms[k] for k in weights if weights[k]>0}
        priority=sum(parts.values())
        objective='comparative_control_candidate' if strict_control else 'retake_or_review' if follow>.25 else 'terrain_susceptibility_check' if terrain>=.65 else 'historical_change_check' if change is not None and weights['historical_change']>0 and change>=.65 else 'coverage_gap'
        labels=dict(terrain='relative 2024 terrain susceptibility',follow_up='nearby retake/review need',coverage_gap='gap in accepted site coverage',historical_change='attributed historical terrain change',control='stable relative comparison-site suitability',diversity='underrepresented candidate site type')
        reason=[labels[k] for k in sorted(parts,key=lambda k:(-parts[k],k))[:3] if parts[k]>0]
        scored.append({**c,'priority_score':round(priority,8),'objective':objective,'reason':reason,'components':terms,'weighted_points':parts,'nearest_accepted_m':None if not math.isfinite(dacc[i]) else round(float(dacc[i]),3),'nearest_review_m':None if not math.isfinite(dreview[i]) else round(float(dreview[i]),3),'strict_control_eligible':strict_control})
    scored.sort(key=lambda c:(-c['priority_score'],c['candidate_id']))
    selected=[];type_count=Counter();permission_count=0;selected_ids=set()
    def choose(rows,count):
        nonlocal permission_count
        for c in rows:
            if count<=0 or len(selected)>=cfg.recommendations:return
            if c['candidate_id'] in selected_ids:continue
            if any(distance((c['latitude'],c['longitude']),(q['latitude'],q['longitude']))<cfg.minimum_spacing_m for q in selected):continue
            cap=cfg.max_school if c['site_type']=='school' else cfg.max_roadside if c['site_type']=='roadside' else cfg.max_other_type
            if type_count[c['site_type']]>=cap or (c['access_status']=='permission_required' and permission_count>=cfg.max_permission):continue
            selected.append(c);selected_ids.add(c['candidate_id']);type_count[c['site_type']]+=1;permission_count+=c['access_status']=='permission_required';count-=1
    if weights['control']>0:choose([c for c in scored if c['strict_control_eligible']],2)
    choose([c for c in scored if c['components']['follow_up']>.25],2)
    choose([c for c in scored if c['components']['terrain']>=.65],3)
    for kind in sorted({c['site_type'] for c in scored}):
        if type_count[kind]==0 and len(type_count)<4:choose([c for c in scored if c['site_type']==kind],1)
    choose(scored,cfg.recommendations-len(selected))
    selected.sort(key=lambda c:(-c['priority_score'],c['candidate_id']))
    result={'method_version':VERSION,'profile':cfg.profile,'weights':weights,'original_v2_weights':ORIGINAL_WEIGHTS,'as_of':now.isoformat(),
      'status':'no_eligible_candidates' if not selected else 'adaptive_with_eligible_observations' if accepted or reviews else 'candidate_only_no_eligible_observations',
      'dataset_version':metadata.get('dataset_version'),'candidate_source_sha256':metadata['source_sha256'],'configuration':asdict(cfg),
      'counts':{'source_candidates':len(candidates),'policy_candidates':len(pool),'ranked':len(scored),'recommended':len(selected),'requested':cfg.recommendations,'eligible_unique_accepted_sites':len(accepted),'eligible_review_sites':len(reviews),'input_observation_rows':len(observations),'excluded_observation_records':len(issues)},
      'observation_issues':issues,'candidate_exclusions':dict(skips),'selection_shortfall':len(selected)<cfg.recommendations,
      'recommendations':[dict(c,rank=i+1) for i,c in enumerate(selected)],'scientific_validation':'not_run','synthetic_test_only':allow_synthetic or metadata.get('evidence_kind')=='synthetic_test','limitations':LIMITATIONS}
    result['input_hash']=sha_object({'metadata':metadata,'config':asdict(cfg),'observations':observations,'as_of':now.isoformat(),'site_types':site_types})
    result['plan_hash']=sha_object(result)
    return result
