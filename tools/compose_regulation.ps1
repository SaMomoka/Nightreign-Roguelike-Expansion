param(
    [Parameter(Mandatory=$true)][string]$RelicFile,
    [Parameter(Mandatory=$true)][string]$RewardFile,
    [Parameter(Mandatory=$true)][string]$RelicHash,
    [Parameter(Mandatory=$true)][string]$RewardHash,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$ProjectRoot='E:\Codex\Project\黑环mod'
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$local=[IO.Path]::GetFullPath((Join-Path $root 'local'))+[IO.Path]::DirectorySeparatorChar
$output=[IO.Path]::GetFullPath($OutputDirectory)
if(-not $output.StartsWith($local,[StringComparison]::OrdinalIgnoreCase)){throw 'Output outside project/local'}
if(Test-Path -LiteralPath $output){throw 'Output already exists'}
$source=Join-Path $root 'local\inputs\regulation.bin'
$pinned='876A3CA279A4561D0C69F81FE5E510C75C59AB9A8A201694F8CF4A42C91E0268'
if((Get-FileHash -LiteralPath $source).Hash -ne $pinned){throw 'Original hash mismatch'}
if((Get-FileHash -LiteralPath $RelicFile).Hash -ne $RelicHash -or
   (Get-FileHash -LiteralPath $RewardFile).Hash -ne $RewardHash){throw 'Input package changed'}
$lib=Join-Path $root 'local\tools\Smithbox-2.2.6'
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
function Digest($bytes){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes.ToArray()))}
function Check-Identity($a,$b){
    if($a.Version -ne $b.Version -or $a.Files.Count -ne $b.Files.Count){throw 'Bundle structure changed'}
    for($i=0;$i -lt $a.Files.Count;$i++){
        $x=$a.Files[$i];$y=$b.Files[$i]
        if($x.ID -ne $y.ID -or $x.Name -ne $y.Name -or $x.Flags -ne $y.Flags){throw 'Resource identity changed'}
    }
}
$base=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($source)
$left=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($RelicFile)
$right=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($RewardFile)
Check-Identity $base $left
Check-Identity $base $right
$selected=@();$leftCount=0;$rightCount=0
for($i=0;$i -lt $base.Files.Count;$i++){
    $entry=$base.Files[$i];$a=$left.Files[$i];$b=$right.Files[$i]
    $name=[IO.Path]::GetFileNameWithoutExtension($entry.Name)
    $original=Digest $entry.Bytes
    $changedLeft=(Digest $a.Bytes) -ne $original
    $changedRight=(Digest $b.Bytes) -ne $original
    if($changedLeft -and $changedRight){throw "Conflicting resource: $name"}
    if($changedLeft){
        if($name -notin @('EquipParamAntique','ShopLineupParam')){throw "Unexpected relic resource: $name"}
        $entry.Bytes=$a.Bytes;$leftCount++
    }
    if($changedRight){
        if($name -notin @('ItemTableParam','ItemLotParam_enemy')){throw "Unexpected reward resource: $name"}
        $entry.Bytes=$b.Bytes;$rightCount++
    }
    $origin=if($changedLeft){'relic'}elseif($changedRight){'rewards'}else{'original'}
    $selected += [ordered]@{resource=$name;origin=$origin;sha256=(Digest $entry.Bytes)}
}
if($leftCount -ne 2 -or $rightCount -lt 1){throw 'Expected relic and reward changes'}
New-Item -ItemType Directory -Path $output | Out-Null
$candidate=Join-Path $output 'regulation.unverified.bin'
[SoulsFormats.SFUtil]::EncryptNightreignRegulation($candidate,$base,$base.Compression)
$decoded=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($candidate)
Check-Identity $base $decoded
for($i=0;$i -lt $decoded.Files.Count;$i++){
    if((Digest $decoded.Files[$i].Bytes) -ne $selected[$i].sha256){throw 'Roundtrip resource mismatch'}
}
$final=Join-Path $output 'regulation.bin'
Move-Item -LiteralPath $candidate -Destination $final
[ordered]@{status='BUILD_VERIFIED_GAME_PENDING';source_sha256=$pinned;
    relic_sha256=$RelicHash;reward_sha256=$RewardHash;
    output_sha256=(Get-FileHash -LiteralPath $final).Hash;
    relic_resources=$leftCount;reward_resources=$rightCount;
    resource_count=$selected.Count;all_resources_roundtrip_verified=$true;
    resources=$selected;game_verified=$false} | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $output 'build-report.json') -Encoding utf8
Write-Output "Verified $($selected.Count) resources; relic=$leftCount rewards=$rightCount"
