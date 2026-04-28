SELECT
    coalesce(sum(temp_files), 0)::int AS temp_files,
    coalesce(sum(temp_bytes), 0)::bigint AS temp_bytes
FROM pg_stat_database;
