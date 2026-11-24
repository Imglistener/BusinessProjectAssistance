# Put the app online from this computer, as long as this window stays open (docs/hosting.md).
#   .\go-online.ps1           start (asks for your settings the first time)
#   .\go-online.ps1 -Setup    ask for the settings again
param([switch]$Setup)

$arguments = @("$PSScriptRoot\scripts\go-online.mjs")
if ($Setup) { $arguments += "--setup" }
& node @arguments
exit $LASTEXITCODE
