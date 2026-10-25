"""Stateless Render API. Candidate data frozen at startup; observations never saved."""
import os, json, hashlib, secrets, asyncio
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from .engine import Config, VERSION, rank_candidates

ROOT=Path(__file__).resolve().parents[1]
app=FastAPI(title='EcoSignal Adaptive Planner',version='3.0.0')
lock=asyncio.Semaphore(1)
class Query(BaseModel):
    model_config=ConfigDict(extra='forbid')
    observations:list[dict]=Field(default_factory=list,max_length=5000)
    limit:int=Field(default=10,ge=1,le=50)
    site_types:list[str]|None=Field(default=None,max_length=20)

def load_data():
    directory=Path(os.environ.get('PLANNER_DATA_DIR',str(ROOT/'data')))
    raw=(directory/'candidates.json').read_bytes();meta=json.loads((directory/'manifest.json').read_text())
    if not isinstance(meta,dict):raise ValueError('Invalid candidate manifest')
    if hashlib.sha256(raw).hexdigest()!=meta.get('candidates_sha256'):raise ValueError('Candidate integrity failure')
    rows=json.loads(raw)
    if meta.get('evidence_kind') in ('synthetic','synthetic_test','fixture','example'):raise ValueError('Synthetic candidate pools cannot be deployed as real data')
    cfg=Config(**json.loads((ROOT/'config.json').read_text()))
    from .engine import validate_pool
    validate_pool(rows,meta,cfg)
    if not rows:raise ValueError('Real screened candidate data required')
    return rows,meta,cfg
try:DATA=load_data();DATA_ERROR=None
except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):DATA=None;DATA_ERROR='Real candidate data/configuration missing or invalid'

def authenticate(request:Request):
    token=os.environ.get('PLANNER_API_TOKEN','')
    if not token:raise HTTPException(503,'Planner server token is not configured')
    auth=request.headers.get('Authorization','')
    if not secrets.compare_digest(auth,'Bearer '+token):raise HTTPException(401,'Unauthorized')

async def parse_query(request:Request):
    if not request.headers.get('content-type','').lower().startswith('application/json'):raise HTTPException(415,'Send JSON')
    body=bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body)>2*1024*1024:raise HTTPException(413,'Planner metadata exceeds2MiB; send no images')
    try:
        def bad_number(value):raise ValueError('Nonfinite JSON number')
        payload=json.loads(body,parse_constant=bad_number)
        return Query.model_validate(payload)
    except (ValueError,TypeError,ValidationError):raise HTTPException(422,'Invalid planner request schema')

@app.get('/health')
def health():return {'status':'ok','method_version':VERSION,'ready':DATA is not None and bool(os.environ.get('PLANNER_API_TOKEN')),'real_candidate_rows':len(DATA[0]) if DATA else 0,'data_status':'verified' if DATA else DATA_ERROR,'observations_persisted':False}

@app.post('/sampling/recommend',dependencies=[Depends(authenticate)])
async def recommend(query:Query=Depends(parse_query)):
    if DATA is None:raise HTTPException(503,'Upload a verified real candidate package before requesting plans')
    candidates,meta,cfg=DATA
    cfg=Config(**{**cfg.__dict__,'recommendations':query.limit})
    async with lock:
        try:return await run_in_threadpool(rank_candidates,candidates,query.observations,meta,cfg,site_types=query.site_types)
        except (ValueError,TypeError):raise HTTPException(422,'Planner inputs failed validation; inspect exported source metadata')
