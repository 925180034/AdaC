"""Configuration management via pydantic-settings + default.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_YAML_PATH = Path(__file__).parent.parent / "configs" / "default.yaml"


def _load_yaml() -> dict[str, Any]:
    if _YAML_PATH.exists():
        with _YAML_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


_yaml = _load_yaml()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 服务 ──────────────────────────────────────────────────────────────
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080

    # ── 数据路径 ──────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///data/metadata.db"
    DATA_DIR: str = "./data"
    CKPT_PATH: str = "./data/ckpt.db"
    ARTIFACTS_DIR: str = "./data/artifacts"

    # ── Qdrant ────────────────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION_TABLES: str = "tbl_embeddings"
    QDRANT_COLLECTION_COLUMNS: str = "col_embeddings"

    # ── LLM ───────────────────────────────────────────────────────────────
    LLM_BASE_URL: str = "http://localhost:8000/v1"
    LLM_API_KEY: str = "EMPTY"
    LLM_MODEL: str = "qwen3.5:9b"
    LLM_TIMEOUT: int = 30

    # ── SBERT ─────────────────────────────────────────────────────────────
    SBERT_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    SBERT_DEVICE: str = "cuda:0"
    SBERT_BATCH_SIZE: int = 256

    # ── TLCF ──────────────────────────────────────────────────────────────
    TLCF_L1_THRESHOLD: float = Field(default=_yaml.get("tlcf", {}).get("theta_1", 0.20))
    TLCF_L2_TOPK: int = Field(default=_yaml.get("tlcf", {}).get("k_2", 40))
    TLCF_L3_TOPK: int = Field(default=_yaml.get("tlcf", {}).get("l3_batch_size", 10))

    # ── Matcher ───────────────────────────────────────────────────────────
    MATCH_DECISION_THRESHOLD: float = Field(
        default=_yaml.get("matcher", {}).get("theta_match", 0.70)
    )
    MATCH_LLM_TOPN: int = Field(
        default=_yaml.get("matcher", {}).get("llm_topn_per_source", 10)
    )

    # ── 多租户 ────────────────────────────────────────────────────────────
    DEFAULT_TENANT_ID: str = "default"

    # ── 算法超参（直接从 YAML 读，供各 Agent 访问） ───────────────────────
    @property
    def tlcf_cfg(self) -> dict[str, Any]:
        """TLCF 全量配置（来自 configs/default.yaml）。"""
        return dict(_yaml.get("tlcf", {}))

    @property
    def matcher_cfg(self) -> dict[str, Any]:
        """Matcher 全量配置。"""
        return dict(_yaml.get("matcher", {}))

    @property
    def profiling_cfg(self) -> dict[str, Any]:
        """Profiling 全量配置。"""
        return dict(_yaml.get("profiling", {}))

    @property
    def llm_cfg(self) -> dict[str, Any]:
        """LLM 全量配置。"""
        return dict(_yaml.get("llm", {}))

    @property
    def planner_cfg(self) -> dict[str, Any]:
        """Planner 全量配置。"""
        return dict(_yaml.get("planner", {}))

    @field_validator("SBERT_DEVICE")
    @classmethod
    def validate_device(cls, v: str) -> str:
        allowed = {"cpu", "cuda", "mps"}
        base = v.split(":")[0]
        if base not in allowed:
            raise ValueError(
                f"SBERT_DEVICE must start with one of {allowed}, got {v!r}"
            )
        return v


settings = Settings()
