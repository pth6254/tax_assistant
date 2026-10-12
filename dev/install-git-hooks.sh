#!/usr/bin/env sh
# Installs a pre-commit hook that refuses commits containing API keys or local .env secrets.
# Run once per clone: sh dev/install-git-hooks.sh
set -e
root=$(git rev-parse --show-toplevel)
hook="$root/.git/hooks/pre-commit"
cat > "$hook" <<'HOOK'
#!/usr/bin/env sh
# Installed by dev/install-git-hooks.sh. Values are never printed.
root=$(git rev-parse --show-toplevel)
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c "import sys; sys.exit(sys.version_info < (3, 8))" 2>/dev/null; then
    exec "$py" "$root/scripts/check_secrets.py" --staged
  fi
done
echo "pre-commit: Python not found; secret check skipped" >&2
HOOK
chmod +x "$hook"
echo "installed $hook"
