-- Get waiting queries - PostgreSQL 9.2+
SELECT
      a.pid AS pid,
      a.application_name AS application_name,
      a.datname AS database,
      a.usename AS user,
      a.client_addr AS client,
      EXTRACT(EPOCH FROM (NOW() - a.{duration_column})) AS duration,
      a.state AS state,
      a.query AS query,
      pg_encoding_to_char(d.encoding) AS encoding,
      l.mode AS mode,
      l.locktype AS type,
      COALESCE(c.relname, '') AS relation
FROM pg_stat_activity AS a
JOIN pg_database AS d ON d.datname = a.datname
JOIN pg_locks AS l ON l.pid = a.pid AND NOT l.granted
LEFT JOIN pg_class AS c ON c.oid = l.relation
WHERE
      a.pid != pg_backend_pid()
      AND a.datname IS NOT NULL
      AND ({dbname_filter} IS NULL OR a.datname ~ {dbname_filter})
      AND EXTRACT(EPOCH FROM (NOW() - a.{duration_column})) >= {min_duration}
ORDER BY EXTRACT(EPOCH FROM (NOW() - a.{duration_column})) DESC;
