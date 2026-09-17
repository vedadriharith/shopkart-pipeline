def load_file(engine, file_name: str, table_name: str, batch_id: str) -> None:
    """Full-refresh one CSV into bronze, then verify row counts.

    Existing tables are TRUNCATEd (not dropped) so dependent views in silver
    stay intact. Truncate and reload run in one transaction, so a failure
    leaves the previous data untouched.
    """
    file_path = RAW_DIR / file_name
    if not file_path.exists():
        raise FileNotFoundError(f"Missing source file: {file_path}")

    ingested_at = datetime.now(timezone.utc).isoformat()
    csv_rows = 0

    with engine.begin() as conn:
        table_exists = inspect(conn).has_table(table_name, schema=SCHEMA)
        if table_exists:
            conn.execute(text(f'TRUNCATE TABLE {SCHEMA}."{table_name}"'))

        chunks = pd.read_csv(
            file_path,
            dtype=str,               # keep every value as raw text in bronze
            keep_default_na=False,   # do not turn strings like "NA" into nulls
            na_values=[""],          # only truly empty cells become NULL
            encoding="utf-8-sig",    # strips a hidden BOM character if present
            chunksize=CHUNK_SIZE,
        )
        for i, chunk in enumerate(chunks):
            chunk["_ingested_at"] = ingested_at
            chunk["_source_file"] = file_name
            chunk["_batch_id"] = batch_id

            # Create the table only on the very first load; afterwards always append
            if_exists = "append" if (table_exists or i > 0) else "replace"
            chunk.to_sql(
                table_name,
                conn,
                schema=SCHEMA,
                if_exists=if_exists,
                index=False,
                method=copy_insert,
            )
            csv_rows += len(chunk)

        db_rows = conn.execute(text(f'SELECT COUNT(*) FROM {SCHEMA}."{table_name}"')).scalar()

    status = "OK" if db_rows == csv_rows else "MISMATCH"
    log.info(f"{status:8} | {SCHEMA}.{table_name:30} | csv={csv_rows:>9,} | db={db_rows:>9,}")
    if status == "MISMATCH":
        raise ValueError(f"Row count mismatch for {table_name}")