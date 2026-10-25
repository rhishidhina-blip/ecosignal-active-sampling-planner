# EcoSignal planner preparation repair

This patch changes preparation only. It does not change the API, numerical GeoRisk grid/CDF, planner scoring weights, observation rules, Site, audience or secrets.

## Diagnosis
GitHub run 40148553627 attempts 2 and 3 passed tests, then canceled preparation at about 11m02s and 13m25s. The checked workflow has cancel-in-progress:false and a 45-minute job timeout. These runs therefore did not reach that configured timeout. Public runner annotations only say "The operation was canceled"; the external cancellation trigger is not established. Do not claim this patch can prevent a platform cancellation.

The original script prints its main output only at completion, permits OSMnx recursive retry/rate-limit waits, and constructs expensive study-wide geometry unions. The patch addresses these code weaknesses while retaining all classification and exclusion rules.

## Apply
Extract this repair ZIP. Copy its files into the existing repository at their exact relative paths, replacing the matching files. Keep all other existing repository files. Do not flatten scripts/ or tests/. No data or reference files should be removed.

In the GitHub website, upload prepare_osm.py and the scripts/ and tests/ folders at repository root. If GitHub will not upload .github, open the existing .github/workflows/prepare-data.yml, click Edit, and replace its entire contents with the workflow in this ZIP. GitHub Desktop can copy all paths including .github directly.

Commit the changes. Start a NEW Actions > Prepare real planner data > Run workflow on main, spacing 240. Do not rerun an old attempt: it retains the old workflow definition even if checkout downloads newer main files.

## Changes
- Ubuntu 24.04 explicitly selected for a stable runner image; the migration notice is not itself evidence of the cancellation cause.
- Unbuffered stage logs, 30-second heartbeats, retained diagnostic artifact, completed OSM request cache preserved on failure where runner teardown permits.
- A 20-minute preparation child deadline produces explicit failure/status; job ceiling 35 minutes.
- Exact spatial-index polygon/nearest-distance screening replaces expensive region-wide geometry unions. Shared polygon boundaries are resolved with small local unions to preserve original semantics. Candidate screening progresses in 1,000-row chunks.
- 120-second individual OSM request timeout, normal server rate limits respected. Global watchdog also bounds recursive retries and rate-limit waits. No partial OSM response is accepted or substituted.
- Original full CDF, all 24 numeric fixtures, candidate source/hash/access checks and fail-closed build guard remain in force. Missing data never become safe candidates.

## Verification
46 software tests passed, including all 24 real numerical terrain fixtures (within the numerical test suite), complete original-vs-indexed synthetic access-screening parity, shared polygon edges, random polygon/road distance parity, child success/failure, heartbeat/deadline termination, API and deployment guards.
Python compilation and workflow YAML parsing passed. Synthetic test inputs are not observations and are not bundled as real candidate data.

This repair has not been committed to the remote repository or run in GitHub Actions. Full live OSM preparation and subsequent Render readiness remain to be verified after applying it. No scientific validation is claimed. If external cancellation recurs, download the preparation diagnostics artifact (if teardown completed) and the job logs; the last logged stage will locate the interruption.

## Test command
PYTHONUNBUFFERED=1 python -m unittest discover -s tests -v

## Preparation command
python -u scripts/run_preparation.py --spacing-m 240 --deadline-seconds 1200
