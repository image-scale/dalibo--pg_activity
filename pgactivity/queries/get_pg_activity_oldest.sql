SELECT
      a.procpid AS pid,
      0 AS xmin,
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
      CASE WHEN a.waiting THEN 'Y' ELSE NULL END AS wait,
      a.procpid AS query_leader_pid,
      false AS is_parallel_worker
FROM pg_stat_activity AS a
JOIN pg_database AS d ON d.datname = a.datname
WHERE
      a.procpid != pg_backend_pid()
      AND a.datname IS NOT NULL
      AND a.current_query NOT LIKE '<IDLE%%'
      AND ({dbname_filter} IS NULL OR a.datname ~ {dbname_filter})
      AND EXTRACT(EPOCH FROM (NOW() - a.{duration_column})) >= {min_duration};
