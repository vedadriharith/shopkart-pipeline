"""Load raw Olist CSV files into the bronze schema (full refresh)."""

import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from db import PROJECT_ROOT, get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "olist"
CHUNK_SIZE = 100_000
SCHEMA = "bronze"

# Map each source CSV file to its bronze table name
FILE_TO_TABLE = {
    "olist_customers_dataset.csv": "customers",
    "olist_geolocation_dataset.csv": "geolocation",
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "product_category_name_translation.csv": "product_category_translation",
}

def copy_insert(table, conn, keys, data_iter):
    """Bulk insert rows using Postgres COPY, which is much faster than INSERT."""
    buffer = io.StringIO()
    csv.writer(buffer).writerows(data_iter)
    buffer.seek(0)

    columns = ", ".join(f'"{key}"' for key in keys)
    target = f'"{table.schema}"."{table.name}"'
    with conn.connection.cursor() as cursor:
        cursor.copy_expert(f"COPY {target} ({columns}) FROM STDIN WITH CSV", buffer)

def load_file(engine, file_name: str, table_name: str, batch_id: str) -> None:
    """Load one CSV file into bronze as all-text columns, then verify row counts."""
    file_path = RAW_DIR / file_name
    if not file_path.exists():
        raise FileNotFoundError(f"Missing source file: {file_path}")

    ingested_at = datetime.now(timezone.utc).isoformat()
    csv_rows = 0

    # One transaction per table: either the whole table loads, or nothing changes
    with engine.begin() as conn:
        chunks = pd.read_csv(
            file_path,
            dtype=str,              # keep every value as raw text in bronze
            keep_default_na=False,  # do not turn strings like "NA" into nulls
            na_values=[""],         # only truly empty cells become NULL
            encoding="utf-8-sig",   # strips a hidden BOM character if present
            chunksize=CHUNK_SIZE,
        )
        for i, chunk in enumerate(chunks):
            chunk["_ingested_at"] = ingested_at
            chunk["_source_file"] = file_name
            chunk["_batch_id"] = batch_id

            chunk.to_sql(
                table_name,
                conn,
                schema=SCHEMA,
                if_exists="replace" if i == 0 else "append",
                index=False,
                method=copy_insert
            )
            csv_rows += len(chunk)

        db_rows = conn.execute(text(f'SELECT COUNT(*) FROM {SCHEMA}."{table_name}"')).scalar()

    status = "OK" if db_rows == csv_rows else "MISMATCH"
    log.info(f"{status:8} | {SCHEMA}.{table_name:30} | csv={csv_rows:>9,} | db={db_rows:>9,}")
    if status == "MISMATCH":
        raise ValueError(f"Row count mismatch for {table_name}")

def main() -> None:
    engine = get_engine()
    batch_id = str(uuid.uuid4())
    log.info(f"Starting bronze load, batch_id={batch_id}")

    with engine.begin() as conn:
        for schema in ("bronze", "silver", "gold"):
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

    for file_name, table_name in FILE_TO_TABLE.items():
        load_file(engine, file_name, table_name, batch_id)

    log.info("Bronze load finished successfully")

if __name__ == "__main__":
    main()