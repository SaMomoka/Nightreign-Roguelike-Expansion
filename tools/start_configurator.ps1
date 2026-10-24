$ErrorActionPreference = 'Stop'
$root=Split-Path -Parent $PSScriptRoot
$catalog=Join-Path $root 'local\evidence\relic-catalog.json'
if(-not (Test-Path -LiteralPath $catalog)){throw 'Missing local catalog; run tools/relic_catalog.py import first.'}
$python=(Get-Command python -ErrorAction Stop).Source
Start-Process -FilePath $python -ArgumentList @((Join-Path $PSScriptRoot 'relic_app.py')) -WindowStyle Hidden
