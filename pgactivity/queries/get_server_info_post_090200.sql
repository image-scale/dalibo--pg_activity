-- Server info query for PostgreSQL 9.2
SELECT
    sum(numbackends)::bigint AS total,
    sum(xact_commit)::bigint AS xact_commit,
    sum(xact_rollback)::bigint AS xact_rollback,
    sum(xact_commit + xact_rollback)::bigint AS xact_count,
    sum(blks_read)::bigint AS blks_read,
    sum(blks_hit)::bigint AS blks_hit,
    CASE WHEN %(skip_db_size)s THEN %(prev_total_size)s
         ELSE coalesce(
             sum(
                 CASE WHEN datname NOT IN ('rdsadmin') OR NOT %(using_rds)s
                      THEN pg_database_size(datname) ELSE 0 END
             )::bigint, 0)
    END AS total_size,
    max(length(datname))::int AS max_dbname_length,
    sum(tup_inserted)::bigint AS insert,
    sum(tup_updated)::bigint AS update,
    sum(tup_deleted)::bigint AS delete,
    extract(epoch from now())::bigint AS epoch,
    (SELECT count(*) FROM pg_stat_activity
        WHERE state = 'active'
        AND ({dbname_filter} IS NULL OR datname ~ {dbname_filter}))::int AS active_connections,
    (SELECT count(*) FROM pg_stat_activity
        WHERE state = 'idle'
        AND ({dbname_filter} IS NULL OR datname ~ {dbname_filter}))::int AS idle,
    (SELECT count(*) FROM pg_stat_activity
        WHERE state = 'idle in transaction'
        AND ({dbname_filter} IS NULL OR datname ~ {dbname_filter}))::int AS idle_in_transaction,
    (SELECT count(*) FROM pg_stat_activity
        WHERE state = 'idle in transaction (aborted)'
        AND ({dbname_filter} IS NULL OR datname ~ {dbname_filter}))::int AS idle_in_transaction_aborted,
    (SELECT count(*) FROM pg_stat_activity WHERE waiting
        AND ({dbname_filter} IS NULL OR datname ~ {dbname_filter}))::int AS waiting,
    (SELECT setting FROM pg_settings WHERE name = 'max_connections')::int AS max_connections,
    NULL::int AS autovacuum_workers,
    (SELECT setting FROM pg_settings WHERE name = 'autovacuum_max_workers')::int AS autovacuum_max_workers,
    NULL::int AS logical_replication_workers,
    NULL::int AS parallel_workers,
    NULL::int AS max_logical_replication_workers,
    NULL::int AS max_parallel_workers,
    NULL::int AS max_worker_processes,
    (SELECT setting FROM pg_settings WHERE name = 'max_wal_senders')::int AS max_wal_senders,
    NULL::int AS max_replication_slots,
    now() - pg_postmaster_start_time() AS uptime
FROM pg_stat_database
WHERE ({dbname_filter} IS NULL OR datname ~ {dbname_filter});
