#!/usr/bin/env python3
"""Initialize SQLite metadata database — creates all tables defined in db/models.py."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine

from adacascade.config import settings
from adacascade.db.models import Base


def main() -> None:
    """Create all SQLAlchemy tables if they do not exist."""
    # Ensure data directory exists
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(settings.DATABASE_URL, echo=True)
    Base.metadata.create_all(engine)
    print(f"[init_db] Database initialized at: {settings.DATABASE_URL}")


if __name__ == "__main__":
    main()
