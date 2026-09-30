# Phase 1: Local Development Skeleton

## Boundaries

- React calls only `GET /api/v1/health` through a typed fetch client.
- FastAPI mounts a health router at `/api/v1` with a Pydantic response model.
- CORS allows explicit local origins; credentials and wildcard access are disabled.
- Every backend request receives a server-generated UUID in `X-Request-ID`.
- Structured logs record method, duration, status, and success without bodies or query strings.
- Health reports process liveness only, not cloud connectivity.
- The dashboard sections are placeholders; there are no counts, maps, AI calls,
  citizen submissions, synthetic datasets, storage connections, or deployments.

## Configuration

The backend resolves the root `.env` relative to its configuration module; existing
process environment values take precedence. Vite uses the same root as `envDir`.
Only `VITE_` variables are exposed to the browser. Never put secrets in them.
The API base URL contains the origin only, without `/api/v1`.
Vite environment changes require restarting the dev server or rebuilding.

## Validation

Backend tests use FastAPI TestClient, explicit CORS origins, and patched environment
loading for configuration tests. No cloud credentials or network services are needed.
Frontend tests mock fetch and cover placeholders, connection states, and malformed responses.
Both suites enforce an 80% coverage minimum. The frontend excludes its rendering entry
point and build configuration from unit coverage; browser smoke checks cover mounting.

Run npm commands from the frontend directory using consistent Windows drive-letter
casing. A lowercase `npm --prefix c:\...` invocation caused duplicate Vitest module
contexts in the assessed environment; `cd C:\...\frontend; npm.cmd test` worked.

## Security and Deployment

This is a local-only, unauthenticated skeleton. Bind servers to loopback.
No service account keys, cloud resources, Dockerfiles, or CI/CD deployment pipeline
are created. Cloud access and production security belong to later authorized phases.