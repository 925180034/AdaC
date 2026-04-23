"""Large-object externalization utilities.

Any intermediate variable > ~1 MB (e.g. similarity_matrix) should be
persisted via save_pkl / load_pkl so that LangGraph checkpoints stay small.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

from adacascade.config import settings


def _artifact_dir(task_id: str) -> Path:
    base = Path(settings.ARTIFACTS_DIR)
    d = base / task_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_pkl(task_id: str, name: str, obj: Any) -> str:
    """Serialize obj to data/artifacts/{task_id}/{name}.pkl.

    Args:
        task_id: Integration task identifier.
        name: Filename stem (e.g. "sim").
        obj: Any picklable Python object.

    Returns:
        Absolute path to the saved file (store this in state, not the object).
    """
    path = _artifact_dir(task_id) / f"{name}.pkl"
    with path.open("wb") as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    return str(path)


def load_pkl(path: str) -> Any:
    """Load a previously saved artifact.

    Args:
        path: Absolute path returned by save_pkl.

    Returns:
        Deserialized object.
    """
    with open(path, "rb") as f:
        return pickle.load(f)
