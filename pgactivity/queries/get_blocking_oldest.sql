-- Get blocking queries - old PostgreSQL
SELECT
      a.procpid AS pid,
      a.application_name AS application_name,
      a.datname AS database,
      a.usename AS user,
      a.client_addr AS client,
      EXTRACT(EPOCH FROM (NOW() - a.{duration_column})) AS duration,
      CASE
        WHEN a.current_query = '<IDLE> in transaction' THEN 'idle in transaction'
        WHEN a.current_query = '<IDLE>' THEN 'idle'
        ELSE 'active'
      END AS state,
      a.current_query AS query,
      pg_encoding_to_char(d.encoding) AS encoding,
      l.mode AS mode,
      l.locktype AS type,
      COALESCE(c.relname, '') AS relation,
      CASE WHEN a.waiting THEN 'Y' ELSE NULL END AS wait
FROM pg_stat_activity AS a
JOIN pg_database AS d ON d.datname = a.datname
JOIN pg_locks AS bl ON bl.pid = a.procpid AND bl.granted
JOIN pg_locks AS l ON l.pid != bl.pid
     AND l.locktype = bl.locktype
     AND NOT l.granted
     AND (
         (bl.transactionid IS NOT NULL AND bl.transactionid = l.transactionid)
         OR (bl.relation IS NOT NULL AND bl.relation = l.relation)
     )
LEFT JOIN pg_class AS c ON c.oid = bl.relation
WHERE
      a.procpid != pg_backend_pid()
      AND a.datname IS NOT NULL
      AND ({dbname_filter} IS NULL OR a.datname ~ {dbname_filter})
      AND EXTRACT(EPOCH FROM (NOW() - a.{duration_column})) >= {min_duration}
ORDER BY EXTRACT(EPOCH FROM (NOW() - a.{duration_column})) DESC;
