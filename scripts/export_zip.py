"""Whitelist runtime deployment ZIP for GitHub/Render or the existing Site importer."""
from pathlib import Path
import json,hashlib,zipfile,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from verify_data import verify

def export(destination):
 status=verify();out=Path(destination);out.parent.mkdir(parents=True,exist_ok=True)
 files=['README.md','requirements.txt','run_server.py','config.json','.python-version','.gitignore',
        'eco_planner/__init__.py','eco_planner/engine.py','eco_planner/api.py','data/candidates.json','data/manifest.json','data/preparation-report.json']
 # The service export retains build validation and the fixed numerical reference.
 files+=['scripts/verify_data.py','prepare_candidates.py']
 files += [str(p.relative_to(ROOT)) for p in (ROOT/'reference/georisk').glob('*') if p.is_file()]
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for f in files:
   if (ROOT/f).is_file():z.write(ROOT/f,'EcoSignal_Adaptive_Planner/'+f)
  z.writestr('EcoSignal_Adaptive_Planner/render.yaml',(ROOT/'render.yaml').read_text())
  z.writestr('EcoSignal_Adaptive_Planner/BUILD_STATUS.json',json.dumps(status,indent=2))
 return {'zip':str(out),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),**status}
if __name__=='__main__':print(json.dumps(export(sys.argv[1] if len(sys.argv)>1 else ROOT/'releases/EcoSignal_Adaptive_Planner_Render.zip'),indent=2))
