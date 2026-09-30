# CivicPulse AI

Multilingual citizen development intelligence POC for the BRICS Innovation Hackathon.
**Phases 1-9:** a local FastAPI backend, React policymaker dashboard, reproducible
synthetic datasets, an ADC-authenticated BigQuery summary API, and a Vertex AI
Gemini request-analysis endpoint with separate LangGraph-orchestrated agents for
English, Hindi, and Kannada.
The dashboard uses live backend APIs. Analysis sends submitted text to Vertex
AI and stores validated requests in BigQuery with dataset-resolved coordinates.
Deterministic hotspot detection, infrastructure gap analysis, and transparent
priority scoring, and evidence-backed recommendations are available through the
API and dashboard. Deployment is not implemented.
Every generated record is labeled **SYNTHETIC / DEMO DATA**.

## Requirements

- Python 3.12 with pip and venv.
- Node.js supported by Vite 8 (20.19+ or 22.12+); tested locally with Node 26.7.0.
- npm; tested with npm 11.19.0.
- No Docker, GCP credentials, or cloud services are required for Phase 1.
- Phase 2 live data access requires gcloud/bq, ADC, an enabled BigQuery API, and
	appropriate permissions. Follow [BigQuery setup](docs/bigquery-setup.md).
- Phase 3 requires Vertex AI access using ADC, not an API key. Follow
  [Gemini setup](docs/gemini-setup.md). No live cloud access is needed for unit tests.

## Configuration

Health and the frontend work without a `.env`. The BigQuery endpoint requires
`GCP_PROJECT_ID`. To create local configuration once, from `civicpulse-ai`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Both apps read the root `.env`. Never commit it.

| Variable | Default / purpose |
| --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000`; backend origin without `/api/v1` |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173`; comma-separated allowlist |
| `GCP_PROJECT_ID` | Your project ID; required for BigQuery and Gemini, no hardcoded fallback |
| `BIGQUERY_DATASET` | `civicpulse` |
| `BIGQUERY_LOCATION` | `asia-south1`; must match the dataset location |
| `BIGQUERY_MAX_BYTES_BILLED` | `100000000`; maximum bytes billed per query |
| `HOTSPOT_REQUEST_THRESHOLD` | `20`; nonnegative integer; a hotspot requires strictly more requests |
| `GCP_REGION` | Vertex AI location; example config uses `global`, independent of BigQuery |
| `GEMINI_MODEL` | Model ID; example config uses `gemini-3.1-flash-lite` |
| `GEMINI_TIMEOUT_SECONDS` | `30`; positive timeout up to 120 seconds, with SDK retries disabled |

`VITE_` variables are public build-time values, never secrets. Restart Vite after
editing the environment. If changing its port, update `CORS_ORIGINS` too.

## Run Locally

Terminal 1, from the workspace root:

```powershell
cd civicpulse-ai\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Terminal 2, from the workspace root:

```powershell
cd civicpulse-ai\frontend
npm.cmd ci
npm.cmd run dev
```

- Dashboard: http://127.0.0.1:5173
- Health: http://127.0.0.1:8000/api/v1/health
- API docs: http://127.0.0.1:8000/docs
- BigQuery summary: http://127.0.0.1:8000/api/v1/dashboard/summary
- Citizen analysis: `POST http://127.0.0.1:8000/api/v1/requests/analyze`

Windows `.cmd` launchers avoid unsigned PowerShell npm script restrictions.
No activation or execution-policy change is required. On macOS/Linux, use
`python3.12 -m venv .venv`, `.venv/bin/python`, and `npm` instead.

The health endpoint returns:

```json
{"status":"healthy","service":"civicpulse-backend"}
```

It checks application liveness only. If the backend stops, the dashboard displays
`Backend unavailable`; reload the page after restarting it.
Uvicorn access logging is disabled above to avoid logging query strings; the app
emits structured request IDs, method, latency, status, and success via its logger.

## Phase 2 Data Setup

From `backend`, after configuring ADC and project access as described in the
[setup guide](docs/bigquery-setup.md):

```powershell
.\.venv\Scripts\python.exe ..\data\scripts\generate_data.py
.\.venv\Scripts\python.exe -m app.services.bigquery_setup --export-schemas
.\.venv\Scripts\python.exe -m app.services.bigquery_setup --load
```

The generator writes 500 requests, 50 locations in 10 fictional districts,
250 infrastructure records, and 250 investment records. The loader creates
explicit-schema tables and refuses to load into nonempty tables.
Schema exports require no cloud access. Do not rerun loads to append duplicates.

The summary returns `total_requests`, `requests_by_category`, `total_population`,
`infrastructure_records`, and `total_investment`, plus currency and synthetic-data
labels. `total_investment` is an exact decimal JSON string in INR, not a float.
Missing configuration, credentials, or BigQuery access returns a safe HTTP 503;
the health endpoint remains available. Restart the backend after config changes.

## Phases 3-4 Gemini Agents

Set `GCP_PROJECT_ID`, `GCP_REGION`, and `GEMINI_MODEL` in the root `.env`.
These three values are required for analysis. The example environment uses the
generally available `gemini-3.1-flash-lite` model at `global`. See the
[setup guide](docs/gemini-setup.md) for ADC, IAM, and the separate live test.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/requests/analyze -ContentType "application/json; charset=utf-8" -Body '{"text":"We need a hospital near our village."}'
```

The response includes `original_text` copied exactly from the request, plus
`language`, `category`, `sub_category`, `problem`, `location_name`, `urgency`, and
`confidence`. Location is null when no named place is given; no coordinates are
generated. Five separate semantic agents use individual structured JSON schemas,
with strict Pydantic models for all intermediate results and shared state:

`START -> Language Detection -> Classification -> Entity Extraction -> Location Extraction -> Urgency Analysis -> Validation -> END`

LangGraph controls this sequence; each semantic agent reads the original text.
Python validates and combines results without another model call. Unsupported
languages stop early; unknown categories become `Other`. Missing or ungrounded
locations become null. Urgency is a model estimate; confidence is the minimum
of the five agent confidence estimates, not a calibrated probability. Neither is
a calculated priority or verified statistic. Phase 5 persists the validated result
after resolving locations against the synthetic dataset.

Invalid input returns 422, malformed model output 502, unavailable cloud access
503, and timeout 504. Every response carries `X-Request-ID`. Logs omit text and raw
model output. Every executed graph node logs its name, request ID, duration, and
success/error category. External LangSmith tracing and graph persistence are disabled.
This unauthenticated endpoint is for local use only. Each successful analysis makes
five billable Gemini calls with no automatic retries. The per-call timeout remains
`GEMINI_TIMEOUT_SECONDS`; the overall asynchronous deadline is five times that value
plus five seconds (155 seconds by default), excluding subsequent BigQuery operations.
No model tools or recommendations are involved.

## Phase 5 Request Storage

Both `POST /api/v1/requests` and `POST /api/v1/requests/analyze` now accept
`{"text":"Demo Village 01 needs a reliable drinking water supply."}` and return
`201 Created` only after a confirmed BigQuery write. Both are storage operations,
not preview endpoints. The server-generated UUID also appears in `X-Request-ID`.

Stored fields: `request_id`, `original_text`, `language`, `category`, `sub_category`,
`problem`, `location_name`, `district`, `latitude`, `longitude`, `urgency`,
`confidence`, and UTC `created_at`. The table retains its synthetic `data_source` label.
Only a unique, case-insensitive, trimmed name match in synthetic `demographics`
supplies coordinates and district. Missing or ambiguous matches leave those three
fields null; a grounded but unmatched location name is retained. No geocoding or
model-generated coordinates are used.

`GET /api/v1/requests?category=Water&district=Demo%20District%2001&language=English`
returns a JSON array, newest first. All filters are optional and combined with AND;
`limit` defaults to 100 and accepts 1-1000. Filter values are SQL parameters.
Invalid input returns 422; storage/read failures return a redacted 503. Retries of
POST create new IDs, so do not blindly retry an uncertain write outcome.

For an existing Phase 2 table, run the schema-only migration from `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.services.bigquery_setup
```

This preserves rows, makes location fields nullable, and adds nullable confidence.
Legacy records retain null confidence. Do not pass `--load` for populated tables.
Runtime ADC needs BigQuery job creation plus dataset read/write access; migration
also needs table schema update permission. See [BigQuery setup](docs/bigquery-setup.md).

The live storage test makes five billable model calls and retains one synthetic row:

```powershell
$env:RUN_REQUEST_STORAGE_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -m requests_live --no-cov --maxfail=1
Remove-Item Env:RUN_REQUEST_STORAGE_INTEGRATION
```

Inference-only `gemini_live` tests invoke the agent directly and do not write rows.

## Phase 6 Demand Hotspots

`POST /api/v1/hotspots/detect` takes no body. It reads synthetic requests and
demographics from BigQuery, aggregates in Python, replaces the derived `hotspots`
snapshot, and returns a JSON array with HTTP 200 after the write completes.
No Gemini calls or ML clustering are used. Original requests remain unchanged.

- Groups: exact `district`, `location_name`, and `category`, using resolved canonical names.
- `request_count`: distinct request IDs across all history through detection time;
	only groups strictly above `HOTSPOT_REQUEST_THRESHOLD` qualify (21 at default 20).
- `affected_population`: the matching demographics population, counted once per group.
	This is a locality-level proxy, not verified affected individuals; do not sum it
	across categories to infer a unique population total.
- `average_urgency`: arithmetic mean across those requests.
- `demand_growth`: `(recent_count - previous_count) / previous_count`, where recent
	covers detection time minus 30 days through detection time, and previous covers
	the preceding 30 days. A value of `1.0` means 100% growth. If previous is zero,
	growth is null when recent is nonzero, otherwise zero. Old requests still count
	toward the all-history threshold even when both growth windows are empty.
- Coordinates and population come only from one unambiguous demographics match
	on district and location. Unresolved/ambiguous groups and future requests are excluded.

`GET /api/v1/hotspots?limit=1000` returns the stored map-ready array ordered by
request count descending, then ID. `limit` accepts 1-1000 (default 1000).
`GET /api/v1/hotspots/{id}` returns one hotspot, or 404 if absent; malformed UUIDs
return 422. Each row contains the metrics above, `hotspot_id`, category, location,
district, latitude, longitude, and UTC `created_at` (snapshot detection time).
IDs are stable for a district/location/category group across repeated detections.
Reads do not run detection automatically. BigQuery/config/data-validation failures
return a redacted 503.

The snapshot is atomically replaced, never appended; an empty detection clears
stale hotspots. Concurrent detections use last-completed-write semantics, not
versioned history. Run detection again after adding requests or changing threshold.
The POC aggregates the bounded demo dataset in memory with BigQuery scan billing
limits; it is not intended as an unbounded production analytics pipeline.

Provision the fifth table using the existing schema-only command from `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.services.bigquery_setup
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/hotspots/detect
Invoke-RestMethod http://127.0.0.1:8000/api/v1/hotspots
```

The original seed data has a maximum of six requests per group, so the default
threshold of 20 currently produces an empty array. For a local demonstration,
explicitly set `HOTSPOT_REQUEST_THRESHOLD=5`, restart the backend, and detect again.
The application default remains 20; no seed requests are fabricated to force hotspots.

The opt-in live check temporarily creates a low-threshold snapshot, verifies map
list/detail reads, then restores a snapshot using the configured threshold:

```powershell
$env:RUN_HOTSPOT_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -m hotspots_live --no-cov --maxfail=1
Remove-Item Env:RUN_HOTSPOT_INTEGRATION
```

It incurs BigQuery operations only and never modifies source requests. Unit tests
use known synthetic rows and mocked BigQuery, including exact threshold boundaries,
growth windows, duplicate IDs, population, coordinates, stale snapshots, and errors.
No frontend map or recommendations are included in Phase 6. Phase 7 extends the
same detection POST to refresh the gap and priority snapshot after hotspot storage.

## Phase 7 Gaps and Priorities

All scoring is deterministic Python, with no Gemini calls. Run
`POST /api/v1/hotspots/detect` to refresh hotspots and their scores. Then use:

- `GET /api/v1/gaps`: stored gap evidence and all score components, ordered by hotspot ID.
- `GET /api/v1/priorities`: the same records ranked by priority descending, with
	unscored records last and hotspot ID as the tie-breaker.

Both GET routes are read-only and accept `limit=1..1000` (default 1000). Scores are
stored in `infrastructure_gaps`, one row per hotspot. Each record includes the
hotspot fields, component scores, priority, raw capacities and INR amounts, capacity
and investment deficits, selected financial year, normalization maxima, data issues,
and `scoring_version="1.0"`. Currency amounts are exact decimal JSON strings;
scores are JSON numbers. `created_at` is the shared hotspot snapshot timestamp.

### Normalization

| Component | Definition on 0-100 |
| --- | --- |
| Demand | `100 * request_count / max_request_count` across current hotspots |
| Infrastructure gap | `100 * max(required_capacity - available_capacity, 0) / required_capacity` |
| Population impact | `100 * affected_population / max_population` across current hotspots |
| Vulnerability | `100 * vulnerability_index` from matching demographics |
| Urgency | `100 * average_urgency` from the hotspot |
| Investment gap | `100 * max(estimated_need_inr - investment_inr, 0) / estimated_need_inr` |

Zero denominators produce zero when the underlying input is known. Scores are
clamped to 0-100 and rounded to two decimal places using decimal ROUND_HALF_UP.
Demand and population are relative to the current hotspot cohort, not absolute
service benchmarks; adding/removing hotspots can change them. The stored maxima
make each result reproducible. Population remains a locality-level proxy, not a
verified count of affected people.

The confirmed formula **adds** all six components:

```text
priority_score = 0.30 * demand_score
							 + 0.20 * infrastructure_gap_score
							 + 0.15 * population_impact_score
							 + 0.15 * vulnerability_score
							 + 0.10 * urgency_score
							 + 0.10 * investment_gap_score
```

Apply the weights to the stored, two-decimal component scores, then round the
total to two decimals with ROUND_HALF_UP. For components `85, 91, 78, 70, 82, 88`,
the priority is **82.90**, not 84. Weights and methodology are versioned in code.

### Source Rules

Match exact district/location/category; demographics match district/location.
Use one unambiguous infrastructure summary per group and the latest available
financial-year investment summary for that group, in INR. Do not sum requirements
across different units or financial years. Identical projected source rows are
deduplicated; differing summaries for the same key/year are ambiguous. Fiscal
years must have the form `2026-27` with consecutive years.

Missing or ambiguous infrastructure, demographic vulnerability, or investment
inputs produce null for the affected score, null priority, and
`scoring_status="insufficient_data"` with `data_issues`. Known components are still
returned. No missing value is silently treated as zero funding or zero coverage.
Negative/non-finite source values and unsupported currencies fail the refresh
with a redacted 503 instead of publishing invented scores. Complete records have
`scoring_status="complete"`.

The two derived tables are individually atomic snapshots, not a cross-table
transaction. Detection returns an error if score persistence fails. GET reads
only score rows whose ID and timestamp match the current hotspot snapshot, so a
failed refresh cannot present an old snapshot as current. Rerun detection after
source changes or a failed refresh. Concurrent runs retain last-completed-write
semantics; a mismatched snapshot can temporarily yield an empty result.

Provision the sixth table without reloading any seed data:

```powershell
.\.venv\Scripts\python.exe -m app.services.bigquery_setup
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/hotspots/detect
Invoke-RestMethod http://127.0.0.1:8000/api/v1/gaps
Invoke-RestMethod http://127.0.0.1:8000/api/v1/priorities
```

The existing `hotspots_live` opt-in test now also checks stored gap/priority records,
independently recomputes their weighted totals, checks descending ranking, and
restores both snapshots using the configured threshold. No source records are
changed. At the default threshold of 20, the current seed dataset has no hotspots,
so both new GET routes correctly return empty arrays. Phase 7 adds no recommendations
or frontend changes.

## Phase 8 Evidence-Backed Recommendations

`POST /api/v1/recommendations/generate` accepts only a hotspot identifier:

```json
{"hotspot_id":"HOTSPOT_UUID_FROM_THE_HOTSPOTS_API"}
```

The backend loads the matching current scored hotspot, its population, request
count, capacity availability and deficit, gap/priority scores, government funding,
financial year, infrastructure asset count, and average service distance when
available. Clients cannot supply or override numerical evidence. Generation requires
complete scores and an unambiguous matching infrastructure record; rerun hotspot
detection after source changes. Default threshold 20 currently yields no eligible
hotspots. Use the documented lower-threshold demo flow explicitly when needed.

The agent runs `START -> recommendation_generation -> recommendation_validation -> END`
in LangGraph, using one structured-output Vertex AI Gemini call through ADC.
It reuses `GCP_PROJECT_ID`, `GCP_REGION`, `GEMINI_MODEL`, and the per-call timeout.
There are no tools, automatic repair loops, API keys, or external tracing. The graph
has an overall asynchronous deadline of the per-call timeout plus five seconds,
excluding evidence reads and storage. Successful generation can incur model charges.

On success, the API returns `201 Created` with `recommended_intervention`,
`reasoning`, `evidence`, `expected_impact`, `confidence`, and `limitations`, plus
`recommendation_id`, `hotspot_id`, UTC `created_at`, and the exact `evidence_snapshot`.
The recommendation UUID also appears in `X-Request-ID`. Creation time marks request
initiation; the evidence includes its separate hotspot detection timestamp.

### Numerical Grounding

The internal model schema uses `evidence_keys`, not model-written evidence values.
Gemini selects approved evidence keys and can reference them in reasoning with
standalone placeholders such as `{{request_count}}.`. Backend code resolves each
placeholder to a complete labelled fact with the original value and unit. It also
constructs the returned evidence list directly from the stored source snapshot.

Validation rejects direct digits, common English cardinal/ordinal number words,
fractions/multipliers, non-ASCII model prose, unknown or uncited placeholders,
duplicate evidence keys, and placeholders embedded in prose that could relabel a
quantity. Model-authored interventions, expected impacts, and limitations must be
qualitative and contain no placeholders. Request count, infrastructure gap score,
and priority score must be cited. Malformed JSON or failed grounding returns 502
and no recommendation is stored. Model confidence is the sole permitted generated
numeric field: an uncalibrated self-assessment on 0-1, not evidence or predicted impact.

This intentionally constrained English output prevents ordinary numerical
fabrication paths; lexical validation is not a proof of all natural-language
semantics. Qualitative reasoning can still be mistaken or misleading. No project
budget, facility quantity, delivery timeline, or quantified benefit is calculated.
Mandatory backend limitations identify synthetic data, population-proxy assumptions,
missing distance where applicable, uncalibrated confidence, and required field review.
Recommendations do not authorize spending, construction, procurement, or policy action.

### Persistence and Reads

Recommendations are appended to the dedicated BigQuery `recommendations` table
only after validation and a second check of the hotspot timestamp. A changed
snapshot returns 409. The check and insert are not a cross-table transaction;
the immutable evidence snapshot is retained even if sources change immediately
afterward. Responses are returned only after the BigQuery load job succeeds.
Repeated POST requests create new recommendation IDs, not an idempotent update.

- `GET /api/v1/recommendations?limit=100`: history ordered newest first, limit 1-1000.
- `GET /api/v1/recommendations/{id}`: one historical recommendation and its evidence.

GET routes do not call Gemini or recalculate advice. Historical recommendations
remain visible after hotspot redetection; inspect `evidence_snapshot.hotspot_created_at`
before treating them as current. Unknown IDs return 404; invalid input 422;
incomplete/stale evidence 409; invalid model output 502; cloud/storage failures 503;
Gemini timeouts 504. Logs contain request IDs, node names, timings, and safe status,
not evidence text, raw model output, credentials, or cloud exception messages.

Provision the seventh table with the schema-only setup command from `backend`.
No seed CSV reload, new credentials, or extra service is needed. The existing ADC
principal needs source reads, query/load job creation, and writes to recommendations.

Tests mock Gemini, including the real structured-output adapter. The optional
BigQuery round-trip test uses mocked Gemini too and retains one clearly labelled
synthetic test recommendation. It temporarily refreshes low-threshold hotspots and
scores, then restores the configured snapshots without changing citizen requests:

```powershell
$env:RUN_RECOMMENDATION_STORAGE_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -m recommendations_live --no-cov --maxfail=1
Remove-Item Env:RUN_RECOMMENDATION_STORAGE_INTEGRATION
```

Phase 8 verification: 278 offline tests passed, 99.85% coverage; the live BigQuery
round trip passed with mocked Gemini. Actual Vertex recommendation quality and
prompt acceptance were not live-tested in this phase. No frontend or later-phase
features were added.

## Phase 9 Policymaker Dashboard

Open http://127.0.0.1:5173 with the backend running on the configured
`VITE_API_BASE_URL`. The dashboard uses React 19, TypeScript, Tailwind, Leaflet,
and React Leaflet. No dashboard totals, coordinates, scores, or advice are seeded
into frontend code. Backend version remains 0.8.0; Phase 9 changes only the frontend
and documentation.

### Dashboard Data

| Section | Backend source |
| --- | --- |
| Total Citizen Requests | `GET /api/v1/dashboard/summary`, `total_requests` |
| Active Hotspots and map | `GET /api/v1/hotspots?limit=1000` |
| Infrastructure Gaps | `GET /api/v1/gaps?limit=1000`, count of positive gap scores; missing scores excluded |
| Priority Areas | `GET /api/v1/priorities?limit=1000`, backend ranking and scores |
| Recommendations | `GET /api/v1/recommendations?limit=1000`, including historical advice |

The three list-based cards describe the loaded snapshot/history, not uncapped
database totals. At the API cap, counts are marked with a plus and a lower-bound
notice. Category filters apply to the map, table, and recommendation history;
overview cards remain global. Priority rows paginate locally in groups of ten.
Recommendations initially show four records, with a Show more action.

The Leaflet map fits API coordinates. Coincident locations share an accessible
marker; its popup lists all categories at those coordinates and the location,
request count, population proxy, priority score, and infrastructure gap.
Only timestamp-matching scores join the map. The same areas are selectable from
the table, including by keyboard. Missing scores are shown as unavailable, not zero.
OpenStreetMap raster tiles require outbound browser access to
`https://tile.openstreetmap.org`; attribution is retained. Tiles are third-party
geographic imagery, not civic evidence. Tile failure leaves coordinates, markers,
and tabular evidence available and produces a warning. No citizen text goes to
the tile provider. This public tile source is for a low-volume local demo, not a
production deployment.

### Demo Workflow

1. The refresh icon performs read-only dashboard reloads. Each data source has
	independent loading/error handling, so one failure does not hide other sections.
2. **Refresh hotspot scores** explicitly calls `POST /api/v1/hotspots/detect`.
	It replaces the two derived snapshots using the existing backend threshold and
	deterministic scoring rules; source requests are unchanged. The dashboard does
	not lower the threshold or synthesize demo hotspots. With the default threshold
	of 20, the current dataset has no eligible areas. For a populated demonstration,
	use the explicit lower-threshold setup in [Phase 6](#phase-6-demand-hotspots).
3. Choose a scored area from a map popup, table, or recommendation-area menu.
	**Generate recommendation** calls the Phase 8 endpoint with only its hotspot ID,
	then reloads the dashboard. This is an explicit, potentially billable Vertex call
	followed by BigQuery storage, never an automatic page-load action.
4. Submit text in the **Citizen Request Analyzer**. The existing
	`POST /api/v1/requests/analyze` LangGraph pipeline detects language, category,
	problem, location, and urgency and saves the request. The UI shows its result
	and refreshes reads. English, Hindi, and Kannada are supported. Input is limited
	to 5,000 characters; blank submissions and duplicate clicks are disabled.
5. Downstream gap/priority values appear only when there is exactly one matching
	district/location/category with a current snapshot timestamp at or after the
	submission timestamp. Refresh hotspot scores explicitly after saving. Advice
	must match that hotspot and exact snapshot; otherwise it remains unavailable
	until explicitly generated. Unresolved or below-threshold requests cannot obtain
	fabricated scores or advice. The UI labels urgency High at 0.70+, Medium at
	0.40+, otherwise Low, while retaining the raw backend score.

Saved recommendations show intervention, reasoning, original evidence, expected
impact, uncalibrated confidence, and expandable limitations/source timestamps.
Historical snapshots are labelled separately; a failed hotspot read shows unknown
freshness, not a claim that history is current. The retained Phase 8 integration
record identifies mocked Gemini output in its limitations. Advice is synthetic,
advisory, and requires human assessment.

Reads have a one-minute client deadline; detection three minutes, recommendation
generation two minutes, and analysis four minutes. Backend timeouts still apply.
Writes are never automatically retried; after a timeout or network failure, the
write outcome can be unknown and users should refresh before resubmitting.
The analyzer warns that text is sent to Vertex and saved in BigQuery; avoid personal
data. No authentication, deployment, later-phase features, or new cloud data writes
were introduced during Phase 9 verification.

Phase 9 validation: 30 hermetic frontend tests, 97.47% statement coverage, plus
TypeScript/production build and lint. Tests cover endpoint payloads, safe errors,
partial loading failures, map grouping/popups, pagination, caps, snapshot matching,
generation, and analysis with mocked APIs. Browser checks used real read APIs and
temporary test-only responses for populated markers at desktop/mobile widths;
test overrides were removed afterward. No new live Gemini call was made.

## Tests and Build

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

From `frontend`:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

Normal tests require no live Gemini, BigQuery, or other network services. Both suites
enforce at least 80% coverage. Frontend dependencies are locked in `package-lock.json`;
backend runtime and test requirements are separated into two requirements files.

The opt-in BigQuery integration test reads the generated CSVs and compares their
totals with the actual summary endpoint. From `backend`, after loading:

```powershell
$env:RUN_BIGQUERY_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -m integration --no-cov
Remove-Item Env:RUN_BIGQUERY_INTEGRATION
```

For the three separate live Gemini checks, from `backend`:

```powershell
$env:RUN_GEMINI_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -m gemini_live --no-cov --maxfail=1
Remove-Item Env:RUN_GEMINI_INTEGRATION
```

This uses only the provided sample texts, makes up to 15 billable model calls, and
stops on the first failure. Normal
tests use mocked responses plus an in-memory HTTP transport for SDK validation.

## Structure

```text
backend/app/           FastAPI entry point, api, core, schemas, agents, services
backend/tests/         Health, CORS, BigQuery, Gemini, synthetic data, and API tests
frontend/src/          Dashboard, components, services, types, and tests
data/synthetic/        Four clearly labeled synthetic CSV datasets
data/schemas/          Seven explicit BigQuery JSON schemas, including recommendation history
data/scripts/          Reproducible multilingual dataset generator
scripts/               Reserved project automation
docs/                  Phase boundaries and architecture notes
```

## Release Notes and CI/CD

0.9.0: Phase 9 React/TypeScript/Tailwind policymaker dashboard with live overview
metrics, Leaflet hotspot map, ranked priority table, recommendation evidence/history,
and multilingual request analyzer. Independent loading/error states, explicit
generation and score refresh, responsive layouts, and mocked frontend tests.
No backend behavior, source data, credentials, threshold, or deployment changes.

0.8.0: Phase 8 typed LangGraph/Vertex recommendation agent, backend evidence
snapshots and numerical-reference validation, immutable BigQuery history,
generate/list/detail APIs, mocked Gemini coverage, and live storage validation.
No Gemini-derived scoring, new source records, frontend features, or deployment.

0.7.0: Phase 7 deterministic infrastructure/funding gaps, six normalized components,
confirmed additive priority formula, auditable source inputs and normalization
references, infrastructure_gaps storage, read-only gap/ranked-priority endpoints,
and formula plus live persistence tests. No model scoring or recommendations.

0.6.0: Phase 6 deterministic demand hotspots, configurable strict request threshold,
demographics-based population/coordinates, 30-day demand growth, stable IDs, atomic
BigQuery snapshot storage, and detection/list/detail APIs with offline and live tests.
No clustering, recommendations, priority scoring, or frontend changes.

0.5.0: Phase 5 BigQuery request persistence through both POST routes, synthetic
location resolution, filtered GET, non-destructive schema migration, and offline
plus opt-in live storage tests. No recommendations or frontend changes.

0.4.0: Phase 4 separate language, classification, entity, location, and urgency
agents with LangGraph orchestration, Pydantic state, deterministic validation,
null unresolved locations, per-node logs, tracing protection, and agent tests.
No persistence, hotspot detection, priority scoring, or frontend changes.

0.3.0: Phase 3 reusable ADC-only Vertex AI Gemini service, strict structured JSON
validation, multilingual request analysis, timeouts, safe errors, request-ID logs,
mocked tests, and separately gated live tests. Frontend and BigQuery writes unchanged.

0.2.0: Phase 2 synthetic CSVs and schemas, ADC BigQuery service, parameterized
queries, capped query billing, empty-only loader, and dashboard summary API.
No frontend analytics wiring or later-phase AI functionality is included.

0.1.0: Phase 1 local skeleton, environment configuration, health endpoint, CORS,
request logging, dashboard placeholders, unit tests, and frontend build checks.
No automated CI/CD or deployment has been configured; Cloud Build and Cloud Run
remain later phases. See [Phase 1 notes](docs/phase-1.md). Do not expose this
unauthenticated local skeleton publicly.