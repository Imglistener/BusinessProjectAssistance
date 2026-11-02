#!/bin/sh
# Encrypt .env into .env.enc (safe to commit), or decrypt it on another PC.
#   ./secrets.sh lock      .env -> .env.enc
#   ./secrets.sh unlock    .env.enc -> .env
# Uses Node if it's installed, otherwise Docker (nothing else to install).
set -e
case "$1" in lock|unlock) ;; *) echo "Use: ./secrets.sh lock | unlock" >&2; exit 1 ;; esac
root="$(cd "$(dirname "$0")" && pwd)"
if command -v node >/dev/null 2>&1; then
  exec node "$root/scripts/envcrypt.mjs" "$1"
fi
exec docker run --rm -it -e ENV_PASSPHRASE --user "$(id -u):$(id -g)" -v "$root:/work" -w /work \
  node:22-alpine node scripts/envcrypt.mjs "$1"
