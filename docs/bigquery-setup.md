# BigQuery Setup

All records are **SYNTHETIC / DEMO DATA**. The original Phase 2 setup provisions
seed data; the later sections document hotspot, scoring, and recommendation storage.
The Phase 9 dashboard consumes these APIs and exposes explicit analysis, detection,
and recommendation actions. Deployment remains out of scope.

## 1. Authenticate and Select the Project

Commands below use Windows PowerShell from the `civicpulse-ai` root.
Replace `YOUR_PROJECT_ID` with your project ID, not its display name.
Use the same authorized Google account for CLI login and Python ADC.

```powershell
gcloud.cmd auth login
gcloud.cmd config set project YOUR_PROJECT_ID
$project = (gcloud.cmd config get-value project).Trim()
gcloud.cmd projects describe $project
gcloud.cmd auth application-default login
gcloud.cmd auth application-default set-quota-project $project
gcloud.cmd services enable bigquery.googleapis.com --project=$project
```

Never download service-account JSON keys or put credentials in the repository.
CLI credentials and ADC are separate. Changing the gcloud project does not change
ADC identity or quota project. A successful CLI check does not establish ADC access.
An `environment` tag advisory does not itself prevent local development.

## 2. IAM and Billing

For one-time dataset creation, the setup principal needs `bigquery.datasets.create`
and permission to create query/load jobs, such as project-level `roles/bigquery.user`.
The dataset creator receives ownership of the new dataset. For an existing dataset,
use project-level `roles/bigquery.jobUser` and dataset-level `roles/bigquery.dataEditor`
for loading; a read-only backend can use dataset-level `roles/bigquery.dataViewer`.
The ADC quota project also requires `serviceusage.services.use`, commonly provided
by `roles/serviceusage.serviceUsageConsumer`. API enablement requires separate
service-management permissions; ask the project administrator if necessary.

An administrator can grant the narrow project-level runtime permissions:

```powershell
$member = "user:YOUR_AUTHORIZED_EMAIL"
gcloud.cmd projects add-iam-policy-binding $project --member=$member --role=roles/bigquery.jobUser
gcloud.cmd projects add-iam-policy-binding $project --member=$member --role=roles/serviceusage.serviceUsageConsumer
```

Grant the dataset-level role through BigQuery dataset sharing. Do not grant Owner
or Editor to the whole project just to run this POC. Do not run IAM changes unless
you administer the project and have confirmed the correct account.

BigQuery storage and queries can incur charges when billing is enabled. The POC
uses tiny batch loads and a default 100 MB maximum-billed-bytes query cap; no
streaming writes. The cap is per query, not a total spending limit. Review the
project's billing/budget settings. BigQuery sandbox limitations, including automatic
table expiration, may apply to projects without billing.

## 3. Local Environment

Create the root `.env` only if it does not already exist, then set `GCP_PROJECT_ID`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Required values:

```dotenv
GCP_PROJECT_ID=YOUR_PROJECT_ID
BIGQUERY_DATASET=civicpulse
BIGQUERY_LOCATION=asia-south1
BIGQUERY_MAX_BYTES_BILLED=100000000
```

`asia-south1` (Mumbai) is the POC default. Choose the location before creating the
dataset; existing dataset locations cannot be changed in place. Set the same
location for every job. `GCP_REGION` is reserved for later phases and is not used
as a BigQuery location. Existing process environment variables override `.env`.
No project ID is hardcoded in application code. Restart Uvicorn after changes.

## 4. Generate and Load (Recommended)

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe ..\data\scripts\generate_data.py
.\.venv\Scripts\python.exe -m app.services.bigquery_setup --export-schemas
.\.venv\Scripts\python.exe -m app.services.bigquery_setup --load
```

The schema export is local only. The loader uses ADC, explicit schemas, strict
UTF-8 CSV parsing, and `WRITE_EMPTY`; it cannot overwrite or append to a nonempty
table. A repeated load intentionally fails, preventing duplicate data. Provisioning
without `--load` is repeatable; it verifies location, synthetic dataset labeling,
and table schemas. Schemas live in `backend/app/schemas/bigquery.py`; the generated
`data/schemas/*.json` files are for the CLI and must be re-exported after changes.

Loads are atomic per table, not across all four tables. After a partial failure,
repair the cause and load only the still-empty table, for example:

```powershell
.\.venv\Scripts\python.exe -m app.services.bigquery_setup --load --table infrastructure
```

The application service's separate `insert_records` operation appends batches and
waits for load completion. It is not a public HTTP endpoint, and is not an upsert:
callers must not retry an already successful insert or assume request-ID uniqueness
is enforced by BigQuery. Normal setup uses the empty-only loader instead.

## 5. Equivalent bq Commands

Use these as an alternative to the Python loader, not after already loading data.
Run from `civicpulse-ai` after generating the CSV and schema files. The variables
must match `.env`; the following uses the documented defaults.

```powershell
$project = (gcloud.cmd config get-value project).Trim()
$dataset = "civicpulse"
$location = "asia-south1"
bq.cmd --project_id=$project --location=$location mk --dataset --description="SYNTHETIC / DEMO DATA - CivicPulse POC" --label=data_source:synthetic "${project}:${dataset}"

$tables = @("citizen_requests", "demographics", "infrastructure", "government_investments")
foreach ($table in $tables) {
    bq.cmd --project_id=$project mk --table --description="SYNTHETIC / DEMO DATA" --label=data_source:synthetic "${project}:${dataset}.${table}" "data/schemas/${table}.json"
    if ($LASTEXITCODE -ne 0) { throw "Table creation failed; stop and inspect existing resources." }
    bq.cmd --project_id=$project --location=$location load --source_format=CSV --encoding=UTF-8 --skip_leading_rows=1 --max_bad_records=0 "${project}:${dataset}.${table}" "data/synthetic/${table}.csv" "data/schemas/${table}.json"
    if ($LASTEXITCODE -ne 0) { throw "CSV load failed; stop and inspect the error." }
}
```

The CLI loop loads only newly created tables; it stops if a table already exists.
`bq load` otherwise appends by default. Do not remove this guard or use `--replace`
on existing data. For strict atomic empty-only behavior, use the Python utility.

Inspect tables and run a value-parameterized query:

```powershell
bq.cmd --project_id=$project ls "${project}:${dataset}"
bq.cmd show --format=prettyjson "${project}:${dataset}.citizen_requests"
$sql = 'SELECT category, COUNT(*) AS request_count FROM `{0}.{1}.citizen_requests` WHERE category = @category GROUP BY category' -f $project, $dataset
bq.cmd --project_id=$project --location=$location query --use_legacy_sql=false --maximum_bytes_billed=100000000 --parameter="category:STRING:Water" $sql
```

Identifiers come from trusted configuration; values use query parameters. BigQuery
does not support binding table names as query parameters. The backend validates
project/dataset identifiers and allows only the four declared table names.
`execute_query` accepts trusted application SQL only; never expose it as a raw-SQL API.

## 6. Validate the Backend

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest
$env:RUN_BIGQUERY_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -m integration --no-cov
Remove-Item Env:RUN_BIGQUERY_INTEGRATION
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

From another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/dashboard/summary | ConvertTo-Json -Depth 4
```

The endpoint returns total requests, counts by category, population (summed once per
location), infrastructure row count, and total investment. All amounts are INR;
`total_investment` is a JSON decimal string preserving BigQuery NUMERIC precision.
`data_source` is always `SYNTHETIC / DEMO DATA`. Empty tables return zero totals.
The label assumes this dedicated dataset contains synthetic records only; do not
mix real data into it. The frontend remains the Phase 1 placeholder dashboard.

Normal tests mock BigQuery and need no credentials or network. The opt-in integration
test compares the live endpoint to all four CSV files and exercises a parameterized
category query. It does not insert extra rows. Generated data tests cover reproducibility,
multilingual content, coordinate consistency, and population/service/funding relationships.

## Troubleshooting

- HTTP 503: verify ADC, `GCP_PROJECT_ID`, API enablement, IAM, location, and table setup.
- `serviceusage.services.use` denied: reauthenticate ADC with the project-authorized
  account and set its quota project; if still denied, ask an administrator for that
  permission. A CLI account switch alone does not update ADC.
- Dataset/table not found: run setup, or check the environment points to the right project.
- Location mismatch: use the existing dataset location; do not silently recreate tables.
- Existing nonempty table: do not rerun the load; query and validate what is already there.
- Different population/amount totals: ensure the CSV seed matches the loaded dataset.

API errors and setup CLI output intentionally omit credentials, raw SQL, and citizen
content. Request IDs and operation/error-type logs help distinguish failures.

## Phase 5 Migration and Storage

From `backend`, run `python -m app.services.bigquery_setup` using the project venv,
without `--load`. The supported legacy request schema is migrated in place: location
name, district, latitude, and longitude become nullable and confidence is added as
a nullable FLOAT. Existing rows retain null confidence; no values are invented.
Unexpected schemas are rejected. Migration requires `bigquery.tables.update`;
runtime requests require query-job creation, dataset reads, and table data writes.
Do not reload the populated tables or change IAM unless needed and authorized.

Both POST request routes validate LangGraph output, resolve a unique location from
synthetic demographics, and wait for a WRITE_APPEND JSON load job to finish before
returning 201. Unresolved locations have null district/coordinates. GET supports
parameterized category, district, and language filters, with a bounded limit.
See the [API and test instructions](../README.md#phase-5-request-storage).

Local schema/CSV regeneration does not modify cloud rows. The generator includes
blank confidence for seed data. The read-only integration test checks original seed
records while allowing additional Phase 5 requests in the summary totals.

## Phase 6 Hotspot Table

The schema-only setup now provisions five tables. `hotspots` is derived and has no
seed CSV; `--load` still targets only the four original seed datasets. Schema export
includes `data/schemas/hotspots.json`. Existing source tables and records are preserved.

Hotspot fields are `hotspot_id`, `location_name`, `district`, `category`,
`request_count`, `affected_population`, `average_urgency`, `demand_growth`,
`latitude`, `longitude`, and `created_at`. Only `demand_growth` is nullable (no
previous-period baseline). The table is labeled synthetic; no model-derived
coordinates or real citizen data are introduced.

Detection reads only synthetic source rows, aggregates distinct request IDs, and
uses demographics once per district/location/category group. It writes an atomic
WRITE_TRUNCATE load job to the derived table, or an atomic DELETE when no group
qualifies. It never truncates or deletes from citizen_requests. Failed source
validation does not replace the prior snapshot. The runtime principal needs read
access to source tables, BigQuery job creation, and updateData/update permissions
for the derived snapshot table. Existing scoped dataset access may already cover it.

See [Phase 6 API and metric definitions](../README.md#phase-6-demand-hotspots).
The request threshold defaults to 20 and uses strictly greater-than comparison.
The current seed dataset does not exceed it. Live validation used a temporary
lower threshold, verified snapshot/list/detail operations, restored the configured
threshold, and confirmed the source request row count was unchanged.

## Phase 7 Gap and Priority Snapshot

The setup utility now provisions six tables and exports six schemas. The four
original seed tables are unchanged. Neither `hotspots` nor `infrastructure_gaps`
is a seed CSV or included in `--load`.

`infrastructure_gaps` stores the hotspot identity, location, map coordinates,
snapshot timestamp, six components, final priority, capacity and investment gaps,
raw source inputs, selected financial year, normalization maxima, data-quality
status, and scoring version. Its schema is exported to
`data/schemas/infrastructure_gaps.json`. Missing evidence and affected scores are
nullable, rather than fabricated; priority is null unless all components are known.
All money evidence uses NUMERIC and is serialized as decimal strings in JSON.

The detection POST refreshes hotspot storage first, then the score snapshot. Each
write is atomic on its own; the two writes are not a single transaction. Gap and
priority reads filter by matching hotspot ID and snapshot timestamp to avoid
serving stale results after a partial failure. Empty detection clears both derived
tables. Source requests, demographics, infrastructure, and investments are never
overwritten. Snapshot replacement is explicitly restricted to the two derived tables.

Runtime permissions cover source reads, query/load jobs, and data/schema updates
on both derived tables. No additional service, model permission, API key, or IAM
change is introduced. See the [scoring definitions](../README.md#phase-7-gaps-and-priorities)
for normalized inputs, confirmed positive weights, missing-data handling, rounding,
and refresh commands. Both GET endpoints are read-only and use bounded query limits.

Phase 7 verification: 223 offline tests passed with 99.81% overall coverage and
100% coverage on the new services/models/routes. The live synthetic detection test
stored scores, independently verified weighted totals and descending ranking via
both GET endpoints, restored the configured snapshots, and confirmed the source
request count was unchanged. No Gemini calls were made for scoring.

## Phase 8 Recommendation History

Schema-only setup now provisions seven tables and exports seven schemas, including
`data/schemas/recommendations.json`. The four seed CSVs and their loader remain
unchanged. Recommendations are never included in seed loads or snapshot replacement.

The table contains recommendation/hotspot IDs, recommended intervention, reasoning,
evidence, expected impact, confidence, limitations, created_at, and evidence_snapshot.
Reasoning, evidence, and limitations are REPEATED STRING arrays; evidence_snapshot
is a validated JSON document stored as STRING and returned as a typed JSON object
by the API. Original evidence labels, units, and values are preserved for audit.

The backend appends only after Gemini output validation and a hotspot timestamp
recheck, waiting for the WRITE_APPEND load job. Read endpoints are parameterized
and preserve historical recommendations after source changes. A recommendation is
advice tied to its captured evidence, not a current factual guarantee. No original
citizen text is included in the recommendation prompt.

The Phase 8 live storage test used mocked Gemini output, persisted one explicitly
labelled synthetic test recommendation, verified list/detail JSON round trips, and
restored hotspot/score snapshots. Source request row counts were unchanged. It did
not call Vertex AI or assess live recommendation quality. See the
[Phase 8 API and grounding contract](../README.md#phase-8-evidence-backed-recommendations).

## Verified Validation

The earlier ADC permission blocker was resolved before Phase 5. The schema migration
preserved all 500 existing citizen requests (500 before, 500 after). The Phase 5
live test then successfully created and retrieved one synthetic Water request using
all three GET filters; the read-only BigQuery integration test also passed.
No seed data was reloaded, and no credentials or IAM policies were changed.