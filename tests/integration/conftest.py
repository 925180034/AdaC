"""Integration test configuration — sets env vars before any adacascade imports."""

from __future__ import annotations

import os
import tempfile

# These MUST be set before any adacascade module is imported.
_tmpdir = tempfile.mkdtemp(prefix="adac_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/metadata.db"
os.environ["CKPT_PATH"] = f"{_tmpdir}/ckpt.db"
os.environ["ARTIFACTS_DIR"] = f"{_tmpdir}/artifacts"
os.environ["SBERT_DEVICE"] = "cpu"
os.environ["QDRANT_URL"] = "http://localhost:6333"
