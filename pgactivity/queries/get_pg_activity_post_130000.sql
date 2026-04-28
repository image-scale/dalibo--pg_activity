SELECT
      a.pid AS pid,
      a.backend_xmin AS xmin,
      a.application_name AS application_name,
      a.datname AS database,
      a.usename AS user,
      a.client_addr AS client,
      EXTRACT(EPOCH FROM (NOW() - a.{duration_column})) AS duration,
      a.state AS state,
      a.query AS query,
      pg_encoding_to_char(d.encoding) AS encoding,
      a.wait_event AS wait,
      coalesce(a.leader_pid, a.pid) AS query_leader_pid,
      a.leader_pid IS NOT NULL AS is_parallel_worker
FROM pg_stat_activity AS a
JOIN pg_database AS d ON d.datname = a.datname
WHERE
      a.pid != pg_backend_pid()
      AND a.datname IS NOT NULL
      AND a.query NOT LIKE '<IDLE%'
      AND a.backend_type = 'client backend'
      AND ({dbname_filter} IS NULL OR a.datname ~ {dbname_filter})
      AND EXTRACT(EPOCH FROM (NOW() - a.{duration_column})) >= {min_duration};
