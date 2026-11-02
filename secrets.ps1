# Encrypt .env into .env.enc (safe to commit), or decrypt it on another PC.
#   .\secrets.ps1 lock      .env -> .env.enc
#   .\secrets.ps1 unlock    .env.enc -> .env
# Uses Node if it's installed, otherwise Docker (nothing else to install).
param([Parameter(Mandatory = $true)][ValidateSet("lock", "unlock")][string]$Command)

$root = $PSScriptRoot
if (Get-Command node -ErrorAction SilentlyContinue) {
    node "$root\scripts\envcrypt.mjs" $Command
} else {
    docker run --rm -it -e ENV_PASSPHRASE -v "${root}:/work" -w /work node:22-alpine node scripts/envcrypt.mjs $Command
}
exit $LASTEXITCODE
