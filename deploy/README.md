# AdaCascade deployment

This package is for the 课题组 target server deployment. Docker verification is expected on the target server because the current development environment cannot run Docker.

## Prerequisites

- Docker Engine with Docker Compose plugin
- NVIDIA Container Toolkit configured for Docker GPU access
- Access to the AdaCascade repository on the target server
- Runtime storage under `/data/xiaoyunhao/adacascade/runtime`

Qdrant is private to the Compose bridge network and is not published on a host port. SQLite is acceptable for the A+B demo deployment.

Ask the server administrator to move Docker's `data-root` to `/data/docker` before building images if `/var/lib/docker` still lives on the small root disk.

## Deployment workflow

Run from the repository root on the target server:

```bash
mkdir -p /data/xiaoyunhao/adacascade/runtime/{tables,artifacts,qdrant,logs}
cp .env.example .env
# edit .env; never commit it
```

For the lab server, set these deployment-local values in `.env`:

```dotenv
CORS_ALLOW_ORIGINS=http://218.199.69.88:13000
LLM_BASE_URL=http://host.docker.internal:8000/v1
SBERT_DEVICE=cuda:0
```

Then start the stack:

```bash
docker compose build
docker compose up -d qdrant
docker compose run --rm backend python scripts/init_db.py
docker compose run --rm backend python scripts/init_qdrant.py
docker compose up -d
docker compose logs -f backend
```

Keep `.env` deployment-local and out of git. Use placeholders from `.env.example` as a starting point, then set the real API key and any target-server origins or limits needed for the demo. Rebuild `frontend` after changing `API_KEY`, because the demo UI embeds the same token at build time. If the host vLLM is not on port 8000, update `LLM_BASE_URL` accordingly.

## Smoke test

1. Open `http://SERVER_IP:13000/?tenant_id=default`.
2. Verify the Dataset selector is visible and usable.
3. Run the benchmark flow with the MIMIC and Wikidata demo datasets.
4. Watch backend logs during the smoke test:

```bash
docker compose logs -f backend
```
