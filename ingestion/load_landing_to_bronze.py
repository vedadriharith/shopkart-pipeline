"""Incrementally load new JSONL files from the landing zone into bronze (exactly-once per file)."""

import hashlib
import json
import logging
import uuid
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from db import PROJECT_ROOT, copy_insert, get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

LANDING_DIR = PROJECT_ROOT / "data" / "landing"
SCHEMA = "bronze"

# Live data goes to separate tables so the full-refresh Olist load never wipes it
ENTITY_TO_TABLE = {
    "orders": "live_orders",
    "order_items": "live_order_items",
    "order_payments": "live_order_payments",
}

CREATE_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS bronze.ingestion_log (
    source_file   TEXT PRIMARY KEY,
    entity        TEXT NOT NULL,
    target_table  TEXT NOT NULL,
    file_sha256   TEXT NOT NULL,
    row_count     INTEGER NOT NULL,
    batch_id      TEXT NOT NULL,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

INSERT_LOG_ROW = text(
    """
    INSERT INTO bronze.ingestion_log
        (source_file, entity, target_table, file_sha256, row_count, batch_id)
    VALUES
        (:source_file, :entity, :target_table, :file_sha256, :row_count, :batch_id)
    """
)

def compute_sha256(path: Path) -> str:
    """Return the SHA-256 fingerprint of a file, read in blocks to save memory."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def read_jsonl_as_text(path: Path) -> pd.DataFrame:
    """Parse a JSON Lines file, keeping every value as raw text (nulls stay null)."""
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}: invalid JSON on line {line_no}") from exc
            rows.append({key: None if value is None else str(value) for key, value in record.items()})
    return pd.DataFrame(rows)

def load_one_file(engine, entity: str, table:str, path: Path, sha256: str, batch_id: str) -> int:
    """Insert one file's rows and its log entry in a single transaction."""
    source_file = path.relative_to(LANDING_DIR).as_posix()
    df = read_jsonl_as_text(path)

    if not df.empty:
        df["_ingested_at"] = pd.Timestamp.now(tz="UTC").isoformat()
        df["_source_file"] = source_file
        df["_batch_id"] = batch_id

    with engine.begin() as conn:
        if not df.empty:
            df.to_sql(table, conn, schema=SCHEMA, if_exists="append", index=False, method=copy_insert)
        conn.execute(
            INSERT_LOG_ROW,
            {
                "source_file": source_file,
                "entity": entity,
                "target_table": f"{SCHEMA}.{table}",
                "file_sha256": sha256,
                "row_count": len(df),
                "batch_id": batch_id,
            },
        )
    return len(df)


def main() -> None:
    engine = get_engine()
    batch_id = str(uuid.uuid4())
    log.info(f"Starting incremental load, batch_id={batch_id}")

    with engine.begin() as conn:
        conn.execute(text(CREATE_LOG_TABLE))
        already_loaded = {
            row.source_file: row.file_sha256
            for row in conn.execute(text("SELECT source_file, file_sha256 FROM bronze.ingestion_log"))
        }

    new_files = skipped_files = changed_files = 0

    for entity, table in ENTITY_TO_TABLE.items():
        entity_dir = LANDING_DIR / entity
        if not entity_dir.exists():
            log.warning(f"No landing folder for {entity}, skipping")
            continue

        # Only complete files: in-progress .tmp files never match this pattern
        for path in sorted(entity_dir.glob("*.jsonl")):
            source_file = path.relative_to(LANDING_DIR).as_posix()
            sha256 = compute_sha256(path)

            if source_file in already_loaded:
                if already_loaded[source_file] != sha256:
                    log.warning(f"CHANGED  | {source_file} was already loaded but its content differs; not reloading")
                    changed_files += 1
                else:
                    skipped_files += 1
                continue

            rows = load_one_file(engine, entity, table, path, sha256, batch_id)
            log.info(f"LOADED   | {source_file:55} | rows={rows:>5} -> {SCHEMA}.{table}")
            new_files += 1

    log.info(f"Done. new={new_files}, skipped={skipped_files}, changed={changed_files}")


if __name__ == "__main__":
    main()