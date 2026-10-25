# Real candidate data required

The code and real numerical terrain reference are included. A real access-screened candidate pool was not supplied to this chat. No candidate rows or lichen observations have been invented.

Run the manual GitHub workflow **Prepare real planner data** before creating the Render service. It writes candidates.json, manifest.json and preparation-report.json here from actual numerical GeoRisk coverage plus current OpenStreetMap retrieval. It stops if retrieval/screening fails.

Alternatively, copy candidates.json and manifest.json from the real Render ZIP produced by the existing planner notebook into this directory. Then run `python scripts/verify_data.py`.

Render's build deliberately refuses missing/invalid/synthetic candidate data instead of deploying a service that pretends it can recommend real sites.
