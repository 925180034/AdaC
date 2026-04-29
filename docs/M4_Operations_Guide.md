# AdaCascade M4 Operations Guide

## Scope

This guide documents the current non-Docker demo/deployment path. The development environment runs inside a restricted container where Docker iptables is unavailable, so the supported M4 path is Qdrant binary + single-worker FastAPI + Vite public demo proxy.

## Environment

Work from the main project path:

```bash
cd /root/AdaC
conda activate adacascade
```

Use `.env.example` as the template for `.env`. Do not commit `.env`.

Important local paths for the shared demo data:

```bash
DATABASE_URL=sqlite:////root/AdaC/data/metadata.db
DATA_DIR=/root/AdaC/data
CKPT_PATH=/root/AdaC/data/ckpt.db
ARTIFACTS_DIR=/root/AdaC/data/artifacts
NO_PROXY=localhost,127.0.0.1
```

## Startup order

### 1. Start Qdrant

```bash
NO_PROXY=localhost,127.0.0.1 bash scripts/start_qdrant.sh
NO_PROXY=localhost,127.0.0.1 python scripts/init_qdrant.py
curl --noproxy '*' http://localhost:6333/healthz
```

Expected health response contains `healthz check passed`.

### 2. Start optional local vLLM

Use this only when validating the local runtime profile or running A100 pressure tests.

```bash
bash scripts/start_llm.sh
curl --noproxy '*' http://localhost:8000/v1/models
```

For development/demo speed, the API runtime can be used instead of local vLLM.

### 3. Start FastAPI

FastAPI must run as a single worker.

```bash
set -a
. /root/AdaC/.env
set +a
DATABASE_URL="sqlite:////root/AdaC/data/metadata.db" \
DATA_DIR="/root/AdaC/data" \
CKPT_PATH="/root/AdaC/data/ckpt.db" \
ARTIFACTS_DIR="/root/AdaC/data/artifacts" \
NO_PROXY="localhost,127.0.0.1" \
PYTHONPATH="/root/AdaC" \
uvicorn adacascade.api.app:app --host 0.0.0.0 --port 6008 --workers 1
```

Health checks:

```bash
curl --noproxy '*' http://localhost:6008/healthz
curl --noproxy '*' -H 'Authorization: Bearer dev-local-token' -H 'X-Tenant-Id: default' http://localhost:6008/runtime/llm
curl --noproxy '*' -H 'Authorization: Bearer dev-local-token' -H 'X-Tenant-Id: default' 'http://localhost:6008/tables?status=READY&limit=1'
```

### 4. Start frontend demo

Use same-origin API proxy for public browser testing.

```bash
VITE_API_BASE_URL="" \
VITE_API_KEY="dev-local-token" \
npm --prefix /root/AdaC/frontend run dev -- --host 0.0.0.0 --port 6006
```

Public entry:

```text
https://u307207-94cd-0c29b003.nmb1.seetacloud.com:8443/?tenant_id=default
```

Proxy checks:

```bash
curl --noproxy '*' -H 'Authorization: Bearer dev-local-token' -H 'X-Tenant-Id: default' 'https://u307207-94cd-0c29b003.nmb1.seetacloud.com:8443/runtime/llm'
curl --noproxy '*' -H 'Authorization: Bearer dev-local-token' -H 'X-Tenant-Id: default' 'https://u307207-94cd-0c29b003.nmb1.seetacloud.com:8443/tables?status=READY&limit=1'
```

## Runtime LLM switching

The UI runtime switch calls the backend runtime API. Equivalent commands:

```bash
curl --noproxy '*' -X PUT \
  -H 'Authorization: Bearer dev-local-token' \
  -H 'X-Tenant-Id: default' \
  -H 'Content-Type: application/json' \
  -d '{"backend":"api"}' \
  http://localhost:6008/runtime/llm

curl --noproxy '*' -X PUT \
  -H 'Authorization: Bearer dev-local-token' \
  -H 'X-Tenant-Id: default' \
  -H 'Content-Type: application/json' \
  -d '{"backend":"local"}' \
  http://localhost:6008/runtime/llm
```

`api` uses `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. `local` uses `LLM_LOCAL_BASE_URL` and `LLM_LOCAL_MODEL`.

Local smoke note: if Retrieval returns an empty ranking, `/integrate` should complete successfully with empty mappings rather than running Matcher across every lake candidate. This is the expected fast path for low-confidence local L3 output.

## Maintenance scripts

Bulk import prepared fixture manifests:

```bash
python scripts/bulk_ingest.py tests/fixtures/toy_lake --status INGESTED --replace
```

Rebuild TF-IDF after bulk ingest or large lake growth:

```bash
python scripts/rebuild_tfidf.py
```

Garbage collect archived table records and table files under `DATA_DIR`:

```bash
python scripts/gc.py --data-dir /root/AdaC/data
```

## Acceptance checks

Run quality gates before marking an M4 slice complete:

```bash
pytest tests/unit/
pytest tests/integration/
npm --prefix frontend run test -- --run
```

Browser smoke test:

1. Open the public entry URL.
2. Confirm Query Table is populated.
3. Switch runtime to API for fast demo or Local for vLLM validation.
4. Run Discover, Match, and Integrate.
5. Confirm the result workspace renders ranking/mappings and the right panel shows exactly four agents.

## Troubleshooting

### API routes return HTML from public URL

The frontend is running without the Vite proxy or `VITE_API_BASE_URL` is not empty. Restart frontend with `VITE_API_BASE_URL=""`.

### Query table dropdown is empty

Check the backend is using the main metadata database, not a worktree-local empty DB:

```bash
curl --noproxy '*' -H 'Authorization: Bearer dev-local-token' -H 'X-Tenant-Id: default' 'http://localhost:6008/tables?status=READY&limit=1'
```

### Runtime shows local when API is expected

The backend process likely did not source `.env`. Restart FastAPI with `. /root/AdaC/.env` before launching uvicorn.

### Port already in use

Inspect listening ports with `/proc` if `ss` or `fuser` is unavailable:

```bash
python - <<'PY'
from pathlib import Path
ports = {6006, 6008, 6333}
listen = {}
for name in ('tcp', 'tcp6'):
    path = Path('/proc/net') / name
    if not path.exists():
        continue
    for line in path.read_text().splitlines()[1:]:
        parts = line.split()
        if parts[3] != '0A':
            continue
        port = int(parts[1].rsplit(':', 1)[1], 16)
        if port in ports:
            listen.setdefault(port, set()).add(parts[9])
print(listen)
PY
```

### Localhost services fail through proxy

Use `NO_PROXY=localhost,127.0.0.1` for Python services and `curl --noproxy '*'` for health checks.
