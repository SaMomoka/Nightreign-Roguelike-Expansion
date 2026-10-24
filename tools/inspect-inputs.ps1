param([Parameter(Mandatory=$true)][string]$GameDir)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $GameDir).Path
$exe = Join-Path $root 'nightreign.exe'
$reg = Join-Path $root 'regulation.bin'
foreach ($p in @($exe,$reg)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Missing input: $p" }
}
[ordered]@{
    captured_utc = [DateTime]::UtcNow.ToString('o')
    game_dir = $root
    exe_file_version = (Get-Item -LiteralPath $exe).VersionInfo.FileVersion
    exe_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    regulation_sha256 = (Get-FileHash -LiteralPath $reg -Algorithm SHA256).Hash
    title_screen_app_version = $null
    title_screen_regulation_version = $null
    game_test_status = 'NOT_RUN'
} | ConvertTo-Json
