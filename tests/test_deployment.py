"""Deployment packaging checks; no live OSM requests and no real observation data."""
from pathlib import Path
import sys,tempfile,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from verify_data import verify
from export_zip import export
class DeploymentTests(unittest.TestCase):
 def test_missing_data_cannot_be_marked_ready(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(ValueError,'Real candidate data missing'):verify(d)
 def test_synthetic_pool_cannot_pass_build_guard(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'candidates.json').write_text('[]');(p/'manifest.json').write_text(json.dumps({'evidence_kind':'synthetic_test'}))
   with self.assertRaisesRegex(ValueError,'Only actual'):verify(p)
 def test_render_configuration_selects_light_runtime_and_build_guard(self):
  text=(ROOT/'render.yaml').read_text();self.assertIn('python scripts/verify_data.py',text);self.assertIn('python run_server.py',text);self.assertIn('/health',text);self.assertIn('generateValue: true',text);self.assertEqual((ROOT/'.python-version').read_text().strip(),'3.12')
  self.assertNotIn('tensorflow',(ROOT/'requirements.txt').read_text().lower());self.assertNotIn('osmnx',(ROOT/'requirements.txt').read_text().lower())
 def test_preparation_workflow_is_explicitly_manual_and_does_not_include_a_secret(self):
  text=(ROOT/'.github/workflows/prepare-data.yml').read_text();self.assertIn('workflow_dispatch:',text);self.assertNotIn('on: push',text);self.assertIn('scripts/prepare_data.py',text);self.assertNotIn('PLANNER_API_TOKEN:',text);self.assertIn('git add BUILD_STATUS.json data/candidates.json data/manifest.json',text)
if __name__=='__main__':unittest.main()
