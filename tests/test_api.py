"""Local TestClient fixtures; no remote service, secrets or field observations."""
import unittest, os
from unittest.mock import patch
from fastapi.testclient import TestClient
from eco_planner import api
from test_engine import pool,metadata,NOW
from eco_planner.engine import Config,rank_candidates
class APITests(unittest.TestCase):
 def test_missing_server_token(self):
  with patch.dict(os.environ,{'PLANNER_API_TOKEN':''}):self.assertEqual(TestClient(api.app).post('/sampling/recommend',json={}).status_code,503)
 def test_bad_auth(self):
  with patch.dict(os.environ,{'PLANNER_API_TOKEN':'synthetic-test-token'}):self.assertEqual(TestClient(api.app).post('/sampling/recommend',json={}).status_code,401)
 def test_unavailable_real_data_returns_503(self):
  with patch.dict(os.environ,{'PLANNER_API_TOKEN':'synthetic-test-token'}),patch.object(api,'DATA',None):
   r=TestClient(api.app).post('/sampling/recommend',json={},headers={'Authorization':'Bearer synthetic-test-token'});self.assertEqual(r.status_code,503)
 def test_valid_contract_with_explicit_synthetic_engine_injection(self):
  real_rank=rank_candidates
  def synthetic_rank(c,o,m,cfg,site_types=None):return real_rank(c,o,m,cfg,now=NOW,site_types=site_types,allow_synthetic=True)
  with patch.dict(os.environ,{'PLANNER_API_TOKEN':'synthetic-test-token'}),patch.object(api,'DATA',(pool(),metadata(),Config())),patch.object(api,'rank_candidates',synthetic_rank):
   c=TestClient(api.app);r=c.post('/sampling/recommend',json={'observations':[],'limit':5},headers={'Authorization':'Bearer synthetic-test-token'});self.assertEqual(r.status_code,200);self.assertTrue(r.json()['synthetic_test_only']);self.assertEqual(len(r.json()['recommendations']),5)
 def test_request_bounds_and_unknown_fields(self):
  with patch.dict(os.environ,{'PLANNER_API_TOKEN':'synthetic-test-token'}):
   c=TestClient(api.app);h={'Authorization':'Bearer synthetic-test-token'}
   for q in [{'limit':0},{'limit':51},{'as_of':'2020-01-01'},{'observations':[{}]*5001}]:self.assertEqual(c.post('/sampling/recommend',json=q,headers=h).status_code,422)
   self.assertEqual(c.post('/sampling/recommend',content=b'x'*(2*1024*1024+1),headers={**h,'Content-Type':'application/json'}).status_code,413)
if __name__=='__main__':unittest.main()
