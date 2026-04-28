#!/bin/bash
set -eo pipefail

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
export CI=true
export TERM=xterm
export PATH="/usr/lib/postgresql/16/bin:$PATH"

cd /workspace/pg_activity
rm -rf .pytest_cache

id testuser >/dev/null 2>&1 || useradd -m testuser
chown -R testuser:testuser /tmp/pytest-of-root 2>/dev/null || true

su testuser -c "
  export PYTHONDONTWRITEBYTECODE=1
  export PYTHONUNBUFFERED=1
  export CI=true
  export TERM=xterm
  export PATH=/usr/lib/postgresql/16/bin:\$PATH
  cd /workspace/pg_activity
  pytest -v --tb=short -p no:cacheprovider --no-cov --postgresql-exec=/usr/lib/postgresql/16/bin/pg_ctl
"

