#!/usr/bin/env bash
set -euo pipefail
umask 077
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root/deployment/twenty"
backup_dir="$project_root/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
running_services="$(docker compose ps --status running --services)"
restore_services=()
for service in server worker; do
  if grep -Fxq "$service" <<< "$running_services"; then restore_services+=("$service"); fi
done
restore_running() {
  if ((${#restore_services[@]})); then docker compose start "${restore_services[@]}"; fi
}
trap restore_running EXIT
if ((${#restore_services[@]})); then docker compose stop "${restore_services[@]}"; fi
docker compose exec -T db pg_dump -U postgres -d twenty -Fc > "$backup_dir/database.dump"
docker compose exec -T db pg_restore --list < "$backup_dir/database.dump" > "$backup_dir/database-contents.txt"
db_image="$(docker compose images -q db)"
docker run --rm --network none -v cra-twenty_server-local-data:/source:ro --entrypoint tar "$db_image" -C /source -czf - . > "$backup_dir/uploads.tar.gz"
cp .env compose.yaml "$backup_dir/"
if [[ -f compose.override.yaml ]]; then cp compose.override.yaml "$backup_dir/"; fi
docker compose images --format json > "$backup_dir/images.json"
(cd "$backup_dir" && sha256sum database.dump uploads.tar.gz .env compose*.yaml > SHA256SUMS)
if [[ -f "$project_root/records/quote-entry/registration.sqlite3" ]]; then
  python3 "$project_root/scripts/quote_entry.py" backup --destination "$backup_dir/quote-registration.sqlite3"
  (cd "$backup_dir" && sha256sum quote-registration.sqlite3 >> SHA256SUMS)
fi
echo "Backup saved: $backup_dir"
