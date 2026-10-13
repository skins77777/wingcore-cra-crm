#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
backup_name="${1:?Provide a backup timestamp directory name}"
[[ "$backup_name" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]
backup_dir="$project_root/backups/$backup_name"
test -f "$backup_dir/database.dump"
cd "$project_root/deployment/twenty"
test_db="cra_restorecheck_$(cat /proc/sys/kernel/random/uuid | tr -d '-')"
docker compose exec -T db createdb -U postgres "$test_db"
cleanup() { docker compose exec -T db dropdb -U postgres "$test_db"; }
trap cleanup EXIT
docker compose exec -T db pg_restore --exit-on-error --no-owner -U postgres -d "$test_db" < "$backup_dir/database.dump"
count_query="SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_type='BASE TABLE';"
original_count="$(docker compose exec -T db psql -U postgres -d twenty -At -c "$count_query")"
restored_count="$(docker compose exec -T db psql -U postgres -d "$test_db" -At -c "$count_query")"
test "$original_count" = "$restored_count"
test "$restored_count" -gt 0
(cd "$backup_dir" && sha256sum -c SHA256SUMS)
tar -tzf "$backup_dir/uploads.tar.gz" > /dev/null
printf '{"RestoreSucceeded":true,"OriginalTables":%s,"RestoredTables":%s,"Backup":"%s","TemporaryDatabaseCleanup":"automatic"}\n' "$original_count" "$restored_count" "$backup_name" > "$project_root/docs/deployment/logs/backup-restore-verification.json"
cat "$project_root/docs/deployment/logs/backup-restore-verification.json"
