# AdaCascade deployment

This package is for the 课题组 target server deployment. Docker verification is expected on the target server because the current development environment cannot run Docker. The known lab-server profile and operational constraints are recorded in [`deploy/LAB_SERVER.md`](LAB_SERVER.md).

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

`.env` is recommended for real deployments but optional for `docker compose config`; the Compose file uses `env_file.required: false`, which requires a modern Docker Compose plugin. Without `.env`, the demo defaults use the repository's development bearer token value, so production deployments must set `API_KEY` explicitly before building the frontend.

For the lab server, set these deployment-local values in `.env`:

```dotenv
CORS_ALLOW_ORIGINS=http://218.199.69.88:13000
PYTORCH_BASE_IMAGE=pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime
LLM_LOCAL_BASE_URL=http://host.docker.internal:8000/v1
LLM_BASE_URL=http://host.docker.internal:8000/v1
NO_PROXY=localhost,127.0.0.1,qdrant,host.docker.internal
no_proxy=localhost,127.0.0.1,qdrant,host.docker.internal
SBERT_DEVICE=cuda:0
```

The backend image default uses PyTorch `2.4.1-cuda12.1-cudnn9-runtime` so NVIDIA Driver 535 servers do not need CUDA 12.4 driver support. The backend container talks to an external OpenAI-compatible vLLM endpoint and installs `requirements.backend.txt`, which intentionally excludes the local vLLM/Torch pin stack from `requirements.txt` to avoid reinstalling CUDA 12.4 wheels. If deploying on a newer driver, you may override `PYTORCH_BASE_IMAGE` explicitly in `.env`.

Then start the stack:

```bash
docker compose build
docker compose up -d qdrant
docker compose run --rm backend python scripts/init_db.py
docker compose run --rm backend python scripts/init_qdrant.py
docker compose up -d
docker compose logs -f backend
```

Keep `.env` deployment-local and out of git. Use placeholders from `.env.example` as a starting point, then set `API_KEY` and any target-server origins or limits needed for the demo. Rebuild `frontend` after changing `API_KEY`, because the demo UI embeds the same token at build time. If the host vLLM is not on port 8000, update both `LLM_LOCAL_BASE_URL` and `LLM_BASE_URL` accordingly.

After bulk ingestion or demo dataset upload, rebuild TF-IDF explicitly before running Discover/Integrate:

```bash
docker compose run --rm backend python scripts/rebuild_tfidf.py --tenant-id default --corpus all
```

For benchmark corpora, rebuild scoped artifacts too:

```bash
docker compose run --rm backend python scripts/rebuild_tfidf.py --tenant-id benchmark --corpus join
docker compose run --rm backend python scripts/rebuild_tfidf.py --tenant-id benchmark --corpus union
```

## Smoke test

1. Open `http://SERVER_IP:13000/?tenant_id=default`.
2. Verify the Dataset selector is visible and usable.
3. Run the benchmark flow with the MIMIC and Wikidata demo datasets.
4. Watch backend logs during the smoke test:

```bash
docker compose logs -f backend
```
