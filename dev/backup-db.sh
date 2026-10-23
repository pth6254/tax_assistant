#!/usr/bin/env bash
# Dumps the database to backups/tax_db-YYYYMMDD-HHMM.dump (custom format) and keeps the newest 7.
# Run in WSL: ./dev/backup-db.sh   Restore: docker exec -i tax_pgvector pg_restore -U postgres -d tax_db --clean < FILE
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root/backups"
file="$root/backups/tax_db-$(date +%Y%m%d-%H%M).dump"
docker exec tax_pgvector pg_dump -U postgres -d tax_db -Fc > "$file.part"
mv "$file.part" "$file"
ls -1t "$root"/backups/tax_db-*.dump | tail -n +8 | xargs -r rm --
echo "backup: $file ($(du -h "$file" | cut -f1))"
