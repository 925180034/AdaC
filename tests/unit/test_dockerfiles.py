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
