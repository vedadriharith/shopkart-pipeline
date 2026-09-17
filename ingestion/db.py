"""Database connection helper for the ShopKart pipeline."""

import os
from pathlib import Path
import csv
import io

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Load variables from the .env file in the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

def get_engine() -> Engine:
    """Create a SQLAlchemy engine for the ShopKart Postgres warehouse."""
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)

def copy_insert(table, conn, keys, data_iter):
    """Bulk insert rows using Postgres COPY, which is much faster than INSERT."""
    buffer = io.StringIO()
    csv.writer(buffer).writerows(data_iter)
    buffer.seek(0)

    columns = ", ".join(f'"{key}"' for key in keys)
    target = f'"{table.schema}"."{table.name}"'
    with conn.connection.cursor() as cursor:
        cursor.copy_expert(f"COPY {target} ({columns}) FROM STDIN WITH CSV", buffer)