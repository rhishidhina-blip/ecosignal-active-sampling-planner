"""Explicit synthetic sizing probe, not a Render or scientific benchmark."""
import sys,json,time,resource
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_engine import metadata,observation
from eco_planner.engine import rank_candidates
now=datetime.now(timezone.utc)
c=[dict(candidate_id=f'SYNTHETIC-BENCH-{i}',latitude=35.701+(i//100)*.0027,longitude=-78.825+(i%100)*.0035,site_type=['park','forest','roadside','other'][i%4],access_status='field_verification_required',georisk_percentile=(i%100),safety_screened=True,eligible_for_sampling=True,screening_source='SYNTHETIC SOFTWARE SIZING ONLY') for i in range(10000)]
obs=[observation(c[i*97],observation_id=f'SYNTHETIC-OBS-{i}',site_id=f'SYNTHETIC-SITE-{i}',captured_at=now.isoformat(),observed_at=now.isoformat()) for i in range(100)]
t=time.perf_counter();r=rank_candidates(c,obs,metadata(),now=now,allow_synthetic=True)
print(json.dumps(dict(evidence='synthetic_runtime_sizing_only',candidates=len(c),observations=len(obs),accepted_sites=r['counts']['eligible_unique_accepted_sites'],recommended=len(r['recommendations']),seconds=time.perf_counter()-t,process_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,limitations='Local process only; not Render latency, concurrent load, cold start or scientific validation.'),indent=2))
