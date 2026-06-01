"""Static checks for Docker build configuration."""

from __future__ import annotations

from pathlib import Path


def _meaningful_lines(path: str) -> list[str]:
    return [
        line.strip()
        for line in Path(path).read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_frontend_base_image_args_are_declared_before_all_from() -> None:
    """Docker ARGs used by FROM must be declared before the first FROM."""
    lines = _meaningful_lines("frontend/Dockerfile")
    first_from = next(index for index, line in enumerate(lines) if line.startswith("FROM "))

    assert "ARG NODE_BASE_IMAGE=node:20-alpine" in lines[:first_from]
    assert "ARG NGINX_BASE_IMAGE=nginx:1.27-alpine" in lines[:first_from]


def test_backend_dockerfile_predownloads_sbert_with_mirror_and_proxy() -> None:
    """Backend image should contain the SBERT model before first startup."""
    dockerfile = Path("Dockerfile.backend").read_text()

    assert "SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" in dockerfile
    assert "HF_ENDPOINT=${HF_ENDPOINT}" in dockerfile
    assert "HTTPS_PROXY=${HTTPS_PROXY}" in dockerfile


def test_compose_backend_env_file_is_optional() -> None:
    """Fresh checkouts should render Compose config before .env exists."""
    compose = Path("docker-compose.yml").read_text()

    assert "env_file:" in compose
    assert "path: .env" in compose
    assert "required: false" in compose


def test_compose_sets_container_safe_llm_urls() -> None:
    """Backend containers should default to the host vLLM endpoint."""
    compose = Path("docker-compose.yml").read_text()

    assert (
        "LLM_LOCAL_BASE_URL: "
        "${LLM_LOCAL_BASE_URL:-http://host.docker.internal:8000/v1}"
    ) in compose
    assert "LLM_BASE_URL: ${LLM_BASE_URL:-http://host.docker.internal:8000/v1}" in compose


def test_compose_proxy_bypass_includes_host_gateway() -> None:
    """Proxy bypass defaults should include host.docker.internal."""
    compose = Path("docker-compose.yml").read_text()

    assert "host.docker.internal" in compose
    assert (
        "NO_PROXY: "
        "${NO_PROXY:-localhost,127.0.0.1,qdrant,host.docker.internal}"
    ) in compose
    assert (
        "no_proxy: "
        "${no_proxy:-localhost,127.0.0.1,qdrant,host.docker.internal}"
    ) in compose


def test_frontend_api_key_default_matches_backend_dev_default() -> None:
    """No-env demo deployments should keep frontend/backend auth aligned."""
    compose = Path("docker-compose.yml").read_text()

    assert "VITE_API_KEY: ${API_KEY:-dev-local-token}" in compose
    assert "VITE_API_KEY: ${API_KEY:-change-me}" not in compose


def test_dockerignore_excludes_large_and_sensitive_context() -> None:
    """Docker build context should not include local runtime or secrets."""
    dockerignore = Path(".dockerignore").read_text()

    for entry in [
        ".git",
        ".env",
        "data",
        "frontend/node_modules",
        "frontend/dist",
        ".pytest_cache",
        ".mypy_cache",
    ]:
        assert entry in dockerignore
