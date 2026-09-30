# Vertex AI Gemini Agents

Phase 3 introduced the reusable Gemini service; Phase 4 adds separate understanding
agents coordinated by LangGraph. Phase 5 now stores validated results through both
POST routes; see [request storage](../README.md#phase-5-request-storage). Phase 7
calculates priority scores in Python, never Gemini. Phase 8 adds a separate
[evidence-backed recommendation agent](../README.md#phase-8-evidence-backed-recommendations)
using the same ADC-only Gemini service. Phase 9 connects these agents to the
[policymaker dashboard](../README.md#phase-9-policymaker-dashboard) through explicit
submission and generation actions. Deployment is not included.

The recommendation agent performs one structured Gemini call over backend-loaded
evidence, followed by deterministic reference validation. Model text must use
qualitative English and approved evidence placeholders; backend code renders the
numeric facts. Direct numerical claims, invalid references, or malformed output
return 502 without storage. Confidence is an uncalibrated model estimate. No tools,
geocoding, external tracing, or model-calculated priorities are introduced. Phase 8
tests mock Gemini, including its structured-output adapter; live Vertex recommendation
generation was not tested. The live BigQuery storage test also uses mocked Gemini.

## Agent Architecture

`backend/app/agents/understanding_agents.py` contains five separate semantic agents:

| Agent | Typed output | Responsibility |
| --- | --- | --- |
| LanguageDetectionAgent | LanguageResult | English, Hindi, Kannada, or Unsupported |
| ClassificationAgent | ClassificationResult | Civic category and English subcategory; Other when unknown |
| EntityExtractionAgent | EntityResult | Facility/service and stated issue normalized into an English problem |
| LocationExtractionAgent | LocationResult | Explicit named location in the original script, otherwise null |
| UrgencyAnalysisAgent | UrgencyResult | Severity/immediacy estimate on 0-1 |

`backend/app/agents/request_agent.py` builds and invokes the LangGraph orchestrator:

`START -> language_detection -> classification -> entity_extraction -> location_extraction -> urgency_analysis -> validation -> END`

Each semantic agent invokes the existing ADC-only `GeminiService.generate_structured`
once with its own schema and instructions. Each reads the original text independently;
prior agents' model-written prose is not fed into subsequent prompts. Pydantic models
in `backend/app/schemas/request_agent.py` validate each output and the shared state.
The final validation node combines results in Python and preserves original text.
An agent error stops execution before later nodes; no fallback fabricates an analysis.

There are five model calls per successful analysis and no retry policy or loops.
The graph is in-memory with no checkpointer or store. LangSmith tracing is explicitly
disabled per invocation, including when enabled by an ambient parent context. Its
library is a LangGraph dependency and is declared explicitly for this privacy control;
no LangSmith account or API key is required. Tested LangGraph version: 1.2.11.

## SDK and Model

The backend uses `google-genai` (tested with 2.24.0), explicitly configured with
`vertexai=True`, a Google Cloud project/location, and Application Default
Credentials. No API key is passed or required. Tests confirm that ambient
`GOOGLE_API_KEY` and `GEMINI_API_KEY` values do not select API-key authentication
when the service supplies explicit ADC credentials.

The example environment selects `gemini-3.1-flash-lite` and `global`.
Google's model documentation, checked on 2026-09-20, lists this model as generally
available with structured output, released 2026-05-07 with retirement no earlier
than 2027-05-07. Availability to a particular project still depends on permissions,
billing, quotas, and service policies. The live validation below is the final check.

- [Model documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-lite)
- [Google model catalog](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/models)
- [Google Gen AI SDK](https://github.com/googleapis/python-genai)

`global` is not a regional data-residency guarantee. Only submit synthetic/non-sensitive
text in this POC. Choose a documented compatible location if residency is required;
do not reuse `BIGQUERY_LOCATION` automatically. Model IDs and region are configuration,
not hardcoded in application code. Google may update product naming in its documentation;
this service uses the SDK's Vertex AI mode and the `aiplatform.googleapis.com` endpoint.

## Authentication and Access

In Windows PowerShell:

```powershell
gcloud.cmd auth login
gcloud.cmd config set project YOUR_PROJECT_ID
$project = (gcloud.cmd config get-value project).Trim()
gcloud.cmd auth application-default login
gcloud.cmd auth application-default set-quota-project $project
gcloud.cmd services enable aiplatform.googleapis.com --project=$project
```

Use the project-authorized account in both browser logins. CLI login and ADC are
separate. Never download service-account JSON keys or commit credentials.
The service explicitly uses its `GCP_PROJECT_ID` as the ADC quota project at runtime;
it does not rewrite your saved credential files or change accounts.

The ADC principal needs Vertex AI invocation permissions, normally
`roles/aiplatform.user`, and `serviceusage.services.use` on the quota project,
normally `roles/serviceusage.serviceUsageConsumer`. A project administrator can run:

```powershell
$member = "user:YOUR_AUTHORIZED_EMAIL"
gcloud.cmd projects add-iam-policy-binding $project --member=$member --role=roles/aiplatform.user
gcloud.cmd projects add-iam-policy-binding $project --member=$member --role=roles/serviceusage.serviceUsageConsumer
```

Do not grant broad Owner/Editor roles or change IAM without authorization. API
enablement requires its own service-management permissions. Confirm billing and
model access in the Google Cloud console. Each live call can incur charges;
the service caps input at 5,000 characters and output at 2,048 tokens, but these
are not a project-wide spending limit.

## Local Configuration

Set these values in `civicpulse-ai/.env` (already ignored by Git):

```dotenv
GCP_PROJECT_ID=YOUR_PROJECT_ID
GCP_REGION=global
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_TIMEOUT_SECONDS=30
```

The first three are required. Process environment values take precedence over
the root `.env`. `GEMINI_TIMEOUT_SECONDS` defaults to 30 and must be greater than
zero and no more than 120. SDK HTTP timeout and an asynchronous deadline bound
each generation; automatic retries are disabled. The orchestrator also applies an
asynchronous deadline of `5 * GEMINI_TIMEOUT_SECONDS + 5` seconds (default 155).
This includes orchestration overhead, but synchronous ADC discovery occurs
during client initialization. SDK clients are closed on success and failure.

From `civicpulse-ai/backend`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

On Windows, stop backend processes using this virtual environment before upgrading
dependencies to avoid locked compiled-module errors. No elevation or execution-policy
change is needed. Restart the server after environment changes.

## API Contract

`POST /api/v1/requests` (also `/api/v1/requests/analyze`), `Content-Type: application/json`:

```json
{"text":"We need a hospital near our village."}
```

Illustrative `201 Created` response (scores and wording vary; not a captured result):

```json
{
  "request_id": "d6ef6380-7db2-4d5f-9347-8f819d82a638",
  "created_at": "2026-09-20T00:00:00Z",
  "district": null,
  "latitude": null,
  "longitude": null,
  "language": "English",
  "category": "Healthcare",
  "sub_category": "Hospital",
  "problem": "Need a nearby hospital",
  "location_name": null,
  "urgency": 0.7,
  "confidence": 0.9,
  "original_text": "We need a hospital near our village."
}
```

`original_text` is copied by application code, never accepted from the model. Leading
and trailing whitespace and Unicode are preserved. Phase 5 stores the original and
analysis in BigQuery before returning the response. Use only synthetic data.

The input must be a nonblank string of at most 5,000 characters; unexpected fields
are rejected. The model's JSON is strictly Pydantic-validated: required fields,
allowed categories/languages, finite scores on 0-1, string limits, no extra fields.
Markdown-fenced, truncated, empty/blocked, or otherwise invalid JSON is not repaired
or silently accepted. A refusal with no valid analysis returns 502.

Supported languages: English, Hindi, Kannada. Unsupported-language classifications
return 422. Categories: Healthcare, Education, Roads, Water, Electricity, and Other
for requests outside those civic categories. `sub_category` and `problem` are concise
English normalizations. Urgency is a semantic severity estimate; confidence is the
minimum of the five uncalibrated agent confidence estimates. This conservative
aggregation is deterministic, not a statistical accuracy guarantee. Neither is a
deterministic priority score.

Location is nullable and must be explicitly named in the input. The system prompt
requires a verbatim name, never a generic reference like 'our village'. Application
code additionally replaces a non-null name not present in the original text with
null (case-insensitive check). This grounds a mention, not its real-world existence
or identity. Missing, ambiguous, or unresolved names are requested as null. There
are no latitude/longitude fields in model output; extra coordinate or statistic
fields are rejected. Phase 5 adds coordinates only from a unique synthetic dataset
match after agent validation. No external geocoding is performed.

The prompt prohibits invented numbers, statistics, budgets, populations, distances,
and other facts, and treats citizen text as untrusted data rather than instructions.
The model has no tools or grounding lookups. Python resolves named locations
against the synthetic dataset after inference. Schema validation cannot prove every
free-text claim is true: analysis is advisory and semantic errors remain possible.
The endpoint does not authorize action or government spending.

## Error and Logging Contract

| HTTP status | Meaning |
| --- | --- |
| 422 | Invalid input or unsupported language |
| 502 | Malformed/schema-invalid agent output or incomplete analysis |
| 503 | Missing config/ADC, permission denial, quota/rate limit, model access, or service failure |
| 504 | Application/transport timeout or upstream timeout response |

Every response includes a server-generated `X-Request-ID`. Structured logs include
that same ID, operation, duration, result, and safe error category, e.g. `VertexHTTP403`.
Request text, credentials, raw model output, and raw cloud exception messages are
not logged by the service. Each executed node logs `operation=request_agent_node`,
`node`, `request_id`, `latency_ms`, `success`, and a safe `error_type`. Keep debug
HTTP logging off. A generation success log indicates schema-valid output; the HTTP
request log records the final result after language and location checks. External
tracing is disabled; never enable state/prompt logging for this endpoint.

## Tests

Normal hermetic tests, from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Tests cover graph execution order, all five agents, exact text preservation, the
three languages, unknown categories, malformed output, score
bounds, extra coordinates, fabricated locations, CORS, cloud failures, cancellation,
strict intermediate state, tracing protection, ADC configuration, and request-ID
node logging. Legacy single-call service tests remain separate from graph tests.
A real SDK test uses an in-memory HTTP
transport and fake OAuth token; it makes no network request and verifies the Vertex
endpoint, JSON schema, and absence of API-key authentication.

Live tests use only these synthetic examples:

- English: "We need a hospital near our village."
- Hindi: "हमारे गांव में अस्पताल बहुत दूर है।"
- Kannada: "ನಮ್ಮ ಗ್ರಾಮದಲ್ಲಿ ಆಸ್ಪತ್ರೆ ತುಂಬಾ ದೂರದಲ್ಲಿದೆ."

```powershell
$env:RUN_GEMINI_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -m gemini_live --no-cov --maxfail=1
Remove-Item Env:RUN_GEMINI_INTEGRATION
```

This performs up to 15 billable model calls and stops on the first failure. It does
not run BigQuery integration tests or write citizen records. It checks language,
Healthcare classification, null location, schema validity, and exact original text,
not a fixed confidence score or exact model wording.

## Current Live Validation

Phase 3 initially encountered a redacted permission error. After the user aligned
the CLI and ADC identities and quota project, all three single-call live examples
passed. No service-account keys were created or IAM policies changed by the app.
The inference-only opt-in tests now invoke the multi-agent orchestrator directly,
with five model calls per example rather than one, and do not persist requests.

Phase 4 validation: all three live English/Hindi/Kannada cases passed through the
five-agent endpoint (15 model calls total, approximately 131 seconds for the suite).
The offline backend suite passed 128 tests with 4 live tests skipped and 99.66%
overall statement coverage; the new agent modules and state models reached 100%.
No BigQuery records were written. One third-party Starlette/AnyIO deprecation
warning remains; it does not affect these results.