# EcoSignal adaptive planner — GitHub / Render backend

This is the lightweight planner API from EcoSignal_Adaptive_Planner_Deployment_v3.ipynb. It is separate from the two heavy .keras image models and the chatbot. EcoSignal v27 already has its matching Sites integration.

## Quick start: GitHub, then Render

1. Create a new GitHub repository. Extract the supplied ZIP and upload the **contents** of its EcoSignal_Adaptive_Planner_Backend folder, including .github/, .python-version and reference/. requirements.txt must be at the repository root. Do not upload only the ZIP file.
2. Real candidate preparation must finish before deployment. Choose ONE:
   - If Colab already produced a real ready Render ZIP, copy its data/candidates.json and data/manifest.json into this repository's data/ folder. Keep their exact bytes. Do not use the Sites adapter ZIP.
   - Otherwise GitHub → Actions → **Prepare real planner data** → Run workflow. Keep spacing 240. This verifies the terrain source, fetches actual OpenStreetMap geometry, screens access and generates the real candidate pool. It commits data files and releases/EcoSignal_Adaptive_Planner_Render.zip to the repository after success. It never invents observed lichen scans. OSM retrieval can be slow or unavailable; a failed run does not produce fake replacements. If repository rules prevent the bot commit, permit the workflow to write to this repository or run the same preparation commands in your existing Colab runtime and upload the outputs manually.
3. Render → New → Web Service → connect this repository → Python. Leave Root Directory empty. Set:
   - Build command: `pip install -r requirements.txt && python scripts/verify_data.py`
   - Start command: `python run_server.py`
   - Health-check path: `/health`
   - Environment: `PLANNER_API_TOKEN` = a newly generated private token. Put it in Render's Environment settings only; no .env file is needed. Render Blueprint users can use render.yaml, which generates this token automatically.
4. Open https://YOUR-SERVICE.onrender.com/health. It must show `ready:true` and nonzero `real_candidate_rows`. A missing token or missing/invalid candidate data is NOT a working planner. The build guard refuses to deploy with missing real candidate data.
5. Configure your existing Site server-side: `ECOSIGNAL_PLANNER_URL` = the new Render base URL, and `ECOSIGNAL_PLANNER_TOKEN` = the same value as Render's PLANNER_API_TOKEN. Do not put either secret into browser code or GitHub. Return to the Site-maintaining chat to configure these values securely. No website rewrite is necessary.

You can instead download releases/EcoSignal_Adaptive_Planner_Render.zip after the GitHub preparation job succeeds and import it into EcoSignal → Observations → Research workspace → Missions & planner. Sites can then rank its candidate pool natively, with no separate Render service. The ZIP supplied in this chat is the preparation-capable repository; its BUILD_STATUS deliberately records missing candidate data until preparation runs.

## What is included

- FastAPI /health and authenticated POST /sampling/recommend.
- Stateless numerical ranking and input/schema checks; no images or device observations are stored.
- Actual 2024 numerical GeoRisk lattice, fixed 1,473,136-sample CDF, metadata/model/DEM hashes and 24 actual numerical sampling fixtures. These support offline preparation/build verification. They are NOT lichen observations. The API does not load this grid into memory to rank each request.
- Preparation scripts and a manual GitHub Actions job. Heavy OSMnx/geopandas dependencies run during preparation, not in the serving process.
- Synthetic unit tests kept only in test code. No candidate examples or observed biological records are seeded.

The code/reference archive has no exported access-screened candidate pool because none was supplied to this chat. It is code-ready, not data-ready. Do not describe a missing-data health response as a deployed functional recommendation service.

## API contract

GET /health (no token): status, ready, real_candidate_rows, method_version.

POST /sampling/recommend: Authorization: Bearer YOUR_PRIVATE_PLANNER_TOKEN; Content-Type: application/json.

Body: `{"observations":[],"limit":10,"site_types":null}`. The Site supplies actual metadata in this schema automatically. Empty observations produce a clearly labelled candidate-only plan after real candidate preparation. Requests are bounded to 2MiB and 5,000 observations; clients cannot change weights, the candidate pool or server clock.

Only real, explicitly confirmed, source/version-attributed, within-coverage, dated records count. Capture freshness <=30 days; accepted coverage must be confirmed and dated within one hour of capture. Repeat records are deduplicated by explicitly confirmed site ID, with location conflicts excluded. Unknown quality remains unknown. Rejected scans create review/retake needs, not accepted coverage.

## Method and limitations

The explicit current_georisk_review_v1 planner profile has terrain .28/.75, review need .24/.75, accepted-site coverage gap .18/.75 and diversity .05/.75. These preserve the ratios of the surviving original terms. Historical-change and control weights are explicitly inactive by default. This is separate from the unified environmental indicator's 35/15/25/25 domain weights; growth form remains unweighted environmental context.

Model ranks are relative 2024 susceptibility on the fixed 20m systematic sampled cohort, not probabilities, predicted depths, arbitrary-location exact 1m predictions or future scores. Numerical sampling is nearest lattice point, never PNG colors or interpolation across gaps. Permissions are not inferred from OSM absence; school permission-required sites are excluded by default. Other access-screened labels still require on-site checks.

Priority, model confidence, ecological concern and demonstrated scientific accuracy are different quantities. Independent scientific validation remains not run. No observed lichen record has been manufactured to make the planner adapt. Historical forecasts and 2040 exploratory shapes are not used.

## Local preparation / tests

Python 3.12 is selected in .python-version. Run:

```
python -m pip install -r requirements-preparation.txt
python -m unittest discover -s tests -v
python scripts/prepare_data.py --spacing-m 240
python scripts/verify_data.py
python scripts/export_zip.py
```

If real candidate data already exists, only requirements.txt and scripts/verify_data.py are needed to deploy. Runtime uses one worker and bounded vector batches. Measure actual memory/latency on the deployed instance; a local synthetic benchmark is not a guarantee of Render cold-start time or available free-tier resources.

Official setup references: https://render.com/docs/deploy-fastapi and https://render.com/docs/python-version. Original source: EcoSignal_Adaptive_Planner_Deployment_v3.ipynb (embedded source SHA256 b233b05d0b65d8cfac2f52fa6ce9c759fe40cdf953dadbf115e4398437a467c1).
