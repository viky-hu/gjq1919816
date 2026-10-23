"""
SQLite database setup for user accounts, node registry, and query logs.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_DIR = _PROJECT_ROOT / "mia_rag_storage"
_DB_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{_DB_DIR / 'api.db'}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
