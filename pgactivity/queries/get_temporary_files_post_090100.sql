SELECT
    count(*)::int AS temp_files,
    coalesce(sum(size), 0)::bigint AS temp_bytes
FROM pg_ls_tmpdir();
