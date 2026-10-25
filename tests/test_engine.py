"""Synthetic software fixtures only. Never installed as production observation data."""
import unittest, math, json, tempfile
from datetime import datetime,timezone,timedelta
from dataclasses import replace
from pathlib import Path
from eco_planner.engine import *
NOW=datetime(2026,10,24,20,0,tzinfo=timezone.utc)
def pool(n=20):return [dict(candidate_id=f'SYNTHETIC-CAND-{i:03d}',latitude=35.73+(i//5)*.015,longitude=-78.80+(i%5)*.015,site_type=['park','forest','roadside','other','school'][i%5],access_status='field_verification_required',georisk_percentile=90-i*3,safety_screened=True,eligible_for_sampling=True,screening_source='SYNTHETIC SOFTWARE FIXTURE') for i in range(n)]
def metadata():return dict(schema='EcoSignal-planner-candidates-v3',evidence_kind='synthetic_test',source_sha256='a'*64,georisk_reference_version='georisk-2024-native-features-20m-sampling-v1',georisk_binary_sha256='cb1bd7e15d47cbbd9d2a4282108061ca17b5d1600c9e13b78c29934f47309ec7',bounds_wgs84=[-78.82763409759329,35.69795304738758,-78.46371247889225,35.97589123264953],dataset_version='SYNTHETIC-NOT-OBSERVED')
def observation(c,**kwargs):
 r=dict(observation_id='SYNTHETIC-OBS',site_id='SYNTHETIC-SITE',site_confirmed=True,latitude=c['latitude'],longitude=c['longitude'],captured_at='2026-10-24T19:00:00Z',observed_at='2026-10-24T19:00:00Z',source='SYNTHETIC TEST ONLY',model_version='test-only',coverage_status='available',coverage_percent=50,coverage_confirmed=True,coverage_confidence=None)
 return {**r,**kwargs}
def run(c=None,obs=None,**kwargs):return rank_candidates(c or pool(),obs or [],metadata(),now=NOW,allow_synthetic=True,**kwargs)
class EngineTests(unittest.TestCase):
 def test_weights_and_limits(self):
  self.assertAlmostEqual(sum(Config().weights.values()),1);self.assertEqual(Config().weights['historical_change'],0);self.assertEqual(Config().weights['control'],0)
  for cfg in [Config(profile='bad'),Config(distance_cap_m=0),Config(recommendations=51),Config(include_permission_required='true')]:
   with self.assertRaises(ValueError):cfg.validate()
 def test_no_observations_is_candidate_only(self):
  r=run();self.assertEqual(r['status'],'candidate_only_no_eligible_observations');self.assertEqual(r['counts']['eligible_unique_accepted_sites'],0);self.assertIsNone(r['recommendations'][0]['nearest_accepted_m'])
 def test_actual_adaptation_changes_plan_after_accepted_site(self):
  c=pool();before=run(c);top=before['recommendations'][0];after=run(c,[observation(top)])
  self.assertEqual(after['counts']['eligible_unique_accepted_sites'],1);self.assertNotIn(top['candidate_id'],[x['candidate_id'] for x in after['recommendations']]);self.assertNotEqual(before['plan_hash'],after['plan_hash'])
 def test_rejected_scan_is_followup_not_coverage(self):
  c=pool();r=run(c,[observation(c[10],coverage_status='rejected_low_confidence',coverage_confirmed=False)])
  self.assertEqual(r['counts']['eligible_unique_accepted_sites'],0);self.assertEqual(r['counts']['eligible_review_sites'],1)
  q=next(v for v in r['recommendations'] if v['candidate_id']==c[10]['candidate_id']);self.assertEqual(q['objective'],'retake_or_review')
 def test_repeat_scans_do_not_increase_independent_site_count(self):
  c=pool()[0];a=observation(c);b=observation(c,observation_id='SYNTHETIC-REPEAT',captured_at='2026-10-24T19:30:00Z',observed_at='2026-10-24T19:30:00Z')
  r=run(obs=[a,b]);self.assertEqual(r['counts']['eligible_unique_accepted_sites'],1)
 def test_missing_confirmation_and_blank_ids_rejected(self):
  for extra in [dict(site_confirmed=None),dict(site_id=' '),dict(observation_id=''),dict(latitude=91),dict(longitude=-181),dict(model_version=''),dict(source='')]:
   r=run(obs=[observation(pool()[0],**extra)]);self.assertEqual(r['counts']['eligible_unique_accepted_sites'],0);self.assertGreater(len(r['observation_issues']),0)
 def test_stale_future_invalid_or_unzoned_dates_rejected(self):
  for d in ['2026-08-01T00:00:00Z','2027-01-01T00:00:00Z','2026-02-30T00:00:00Z','2026-10-24T19:00:00']:
   self.assertEqual(run(obs=[observation(pool()[0],captured_at=d)])['counts']['eligible_unique_accepted_sites'],0)
 def test_exact_30day_freshness_and_alignment(self):
  t=(NOW-timedelta(days=30)).isoformat();r=run(obs=[observation(pool()[0],captured_at=t,observed_at=t)]);self.assertEqual(r['counts']['eligible_unique_accepted_sites'],1)
  r=run(obs=[observation(pool()[0],observed_at='2026-10-24T17:59:59Z')]);self.assertEqual(r['counts']['eligible_unique_accepted_sites'],0)
 def test_duplicate_observation_ids_invalidate_every_copy(self):
  a=observation(pool()[0]);r=run(obs=[a,dict(a)]);self.assertEqual(r['counts']['eligible_unique_accepted_sites'],0)
 def test_conflicting_coordinates_do_not_join(self):
  a=observation(pool()[0]);b=observation(pool()[5],observation_id='SYNTHETIC-OTHER');r=run(obs=[a,b]);self.assertEqual(r['counts']['eligible_unique_accepted_sites'],0);self.assertIn('conflicting',str(r['observation_issues']))
 def test_test_records_excluded_by_default(self):
  r=rank_candidates(pool(),[observation(pool()[0])],metadata(),now=NOW)
  self.assertEqual(r['counts']['eligible_unique_accepted_sites'],0)
 def test_unknown_confidence_is_not_imputed(self):
  r=run(obs=[observation(pool()[0],coverage_confidence=None)]);self.assertEqual(r['counts']['eligible_unique_accepted_sites'],1)
  for q in [float('nan'),-.1,1.1]:self.assertEqual(run(obs=[observation(pool()[0],coverage_confidence=q)])['counts']['eligible_unique_accepted_sites'],0)
 def test_zero_coverage_is_valid(self):self.assertEqual(run(obs=[observation(pool()[0],coverage_percent=0)])['counts']['eligible_unique_accepted_sites'],1)
 def test_spacing_and_caps(self):
  r=run();v=r['recommendations'];self.assertTrue(all(distance((a['latitude'],a['longitude']),(b['latitude'],b['longitude']))>=120 for i,a in enumerate(v) for b in v[i+1:]));self.assertLessEqual(Counter(x['site_type'] for x in v)['roadside'],3)
 def test_no_silent_relaxation_when_candidates_too_close(self):
  c=pool();
  for p in c:p['latitude']=35.8;p['longitude']=-78.7
  r=run(c);self.assertEqual(len(r['recommendations']),1);self.assertTrue(r['selection_shortfall'])
 def test_permission_exclusion_and_explicit_optin(self):
  c=pool();c[0]['access_status']='permission_required';a=run(c);self.assertNotIn(c[0]['candidate_id'],[v['candidate_id'] for v in a['recommendations']]);b=run(c,config=Config(include_permission_required=True));self.assertIn(c[0]['candidate_id'],[v['candidate_id'] for v in b['recommendations']])
 def test_excluded_access_never_recommended(self):
  c=pool();c[0]['access_status']='excluded_private_or_no_access';r=run(c,config=Config(include_permission_required=True));self.assertNotIn(c[0]['candidate_id'],[v['candidate_id'] for v in r['recommendations']])
 def test_full_profile_requires_historical_provenance(self):
  with self.assertRaises(ValueError):run(config=Config(profile='historical_change_complete_v1'))
 def test_historical_profile_rejects_projection_and_accepts_attributed_observed_change(self):
  c=pool()
  for row in c:row['historical_change_score']=.2
  m={**metadata(),'historical_change_provenance':dict(kind='observed_dem_difference',source_sha256='a'*64,period_years=[2022,2024],normalization='fixed absolute height-difference anchors 0 to 1 m')}
  cfg=Config(profile='historical_change_complete_v1')
  r=rank_candidates(c,[],m,cfg,now=NOW,allow_synthetic=True);self.assertAlmostEqual(sum(r['weights'].values()),1)
  for bad in ['unverified',dict(kind='projection',period_years=[2024,2040])]:
   with self.assertRaises(ValueError):rank_candidates(c,[],{**m,'historical_change_provenance':bad},cfg,now=NOW)
 def test_malformed_ids_and_nonfinite_metadata_fail_safely(self):
  for v in [[],{},123,None]:self.assertEqual(run(obs=[observation(pool()[0],observation_id=v)])['counts']['eligible_unique_accepted_sites'],0)
  r=run(obs=[observation(pool()[0],coverage_confidence=float('nan'))]);self.assertEqual(r['counts']['eligible_unique_accepted_sites'],0)
 def test_current_profile_does_not_relabel_missing_change_as_zero(self):
  r=run();self.assertTrue(all(v['components']['historical_change'] is None and not v['strict_control_eligible'] for v in r['recommendations']))
 def test_boundaries_inputs_and_versioning(self):
  c=pool();c[0]['latitude']=0
  with self.assertRaises(ValueError):run(c)
  with self.assertRaises(ValueError):rank_candidates(pool(),[],{**metadata(),'georisk_binary_sha256':'b'*64},now=NOW)
  r=run();self.assertEqual(r['method_version'],VERSION);self.assertEqual(r,run())
 def test_contributions_sum_and_range(self):
  for r in run()['recommendations']:self.assertAlmostEqual(sum(r['weighted_points'].values()),r['priority_score'],7);self.assertTrue(0<=r['priority_score']<=100)
 def test_filter_uses_full_candidate_pool(self):self.assertTrue(all(c['site_type']=='park' for c in run(site_types=['park'])['recommendations']))
 def test_production_native_export_mapping(self):
  flat=observation(pool()[0]);doc={'observations':[{'observation_id':flat['observation_id'],'source':flat['source'],'input':{'site_id':flat['site_id'],'site_confirmed':True,'location':{'lat':flat['latitude'],'lon':flat['longitude']},'captured_at':flat['captured_at'],'lichen':{'coverage_percent':50,'confirmed':True,'observed_at':flat['observed_at'],'source':flat['source'],'version':'test-only'}}}]}
  rows=observations_from_document(doc);self.assertEqual(run(obs=rows)['counts']['eligible_unique_accepted_sites'],1)
if __name__=='__main__':unittest.main()
