param([string]$ProjectRoot='E:\Codex\Project\黑环mod')
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$locator=Get-Content -LiteralPath (Join-Path $root 'local/relic-editor-package.json') -Raw | ConvertFrom-Json
$source=[IO.Path]::GetFullPath($locator.path)
$package=Get-Content -LiteralPath (Join-Path $source 'package.json') -Raw | ConvertFrom-Json
if($package.kind -ne 'relic_editor'){throw 'Expected tested relic editor source'}
foreach($property in $package.sha256.PSObject.Properties){
    $file=[IO.Path]::GetFullPath((Join-Path $source $property.Name))
    if(-not $file.StartsWith($source+[IO.Path]::DirectorySeparatorChar) -or
       (Get-FileHash -LiteralPath $file).Hash -ne $property.Value){throw 'Source package integrity failure'}
}
$id='relic_probe_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[Guid]::NewGuid().ToString('N').Substring(0,6)
$out=Join-Path $root "local/packages/$id"
[IO.Directory]::CreateDirectory($out) | Out-Null
foreach($property in $package.sha256.PSObject.Properties){
    $dest=Join-Path $out $property.Name
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($dest)) | Out-Null
    Copy-Item -LiteralPath (Join-Path $source $property.Name) -Destination $dest
}
$lib=Join-Path $root 'local/tools/Smithbox-2.2.6'
[Environment]::CurrentDirectory=$lib
Set-Location -LiteralPath $lib
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
$plan=Get-Content -LiteralPath (Join-Path $out 'editor-plan.json') -Raw | ConvertFrom-Json
$talk=Join-Path $out 'mod/script/talk/m10_00_00_00.talkesdbnd.dcx'
$bundle=[SoulsFormats.BND4]::Read($talk)
$file=@($bundle.Files | Where-Object {$_.Name.EndsWith('\t605001000.esd')})
if($file.Count -ne 1){throw 'Missing original small jar ESD'}
$esd=[SoulsFormats.ESD]::Read($file[0].Bytes)
$originalNormalized=$esd.Write()
$state=$esd.StateGroups[[long]2147483643][[long]$plan.root_state]
if($null -eq $state){throw 'Missing root menu'}
$markers=@(1599843857,1599843858,1599843859,1599843860)
for($i=0;$i -lt 4;$i++){
    $args=[Collections.Generic.List[byte[]]]::new()
    $args.Add([byte[]](@(0x82)+[BitConverter]::GetBytes([int]$i)+@(0xa1)))
    $args.Add([byte[]](@(0x82)+[BitConverter]::GetBytes([int]$markers[$i])+@(0xa1)))
    $state.EntryCommands.Add([SoulsFormats.ESD+CommandCall]::new(1,100,$args.ToArray()))
}
$file[0].Bytes=$esd.Write()
$bundle.Write($talk)
$roundtrip=[SoulsFormats.BND4]::Read($talk)
$again=[SoulsFormats.ESD]::Read(($roundtrip.Files | Where-Object {$_.Name.EndsWith('\t605001000.esd')}).Bytes)
$commands=$again.StateGroups[[long]2147483643][[long]$plan.root_state].EntryCommands
if(@($commands | Where-Object {$_.CommandBank -eq 1 -and $_.CommandID -eq 100}).Count -ne 4){throw 'Probe roundtrip failed'}
for($i=0;$i -lt 4;$i++){$commands.RemoveAt($commands.Count-1)}
if([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($originalNormalized)) -ne
   [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($again.Write()))){throw 'Unexpected change outside the four probe commands'}
$save="NRE_$id.sl2"
foreach($name in 'generate.me3','play.me3'){
    $profile=(Get-Content -LiteralPath (Join-Path $out $name) -Raw).Replace($package.savefile,$save)
    [IO.File]::WriteAllText((Join-Path $out $name),$profile,[Text.UTF8Encoding]::new($false))
}
$probe=[ordered]@{
    schema_version=1;kind='read_only_work_value_probe';source_package=[IO.Path]::GetFileName($source);
    trigger='Open the small jar root conversation menu';markers=$markers;
    native_command='SetWorkValue 1:100';indices=@(0,1,2,3);
    reference='https://github.com/thefifthmatt/ESDLang/blob/master/dist/ESDScriptingDocumentation_Talk.json';
    runtime_write_enabled=$false;crafting_adapter_verified=$false
}
$probe | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'runtime-probe.json') -Encoding utf8
$manifest=Get-Content -LiteralPath (Join-Path $out 'manifest.json') -Raw | ConvertFrom-Json
$manifest.limitations+= 'Developer work-value probe: not a full catalog release'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'manifest.json') -Encoding utf8
$hashes=[ordered]@{}
foreach($name in @($package.sha256.PSObject.Properties.Name)+@('runtime-probe.json')){
    $hashes[$name]=(Get-FileHash -LiteralPath (Join-Path $out $name)).Hash
}
[ordered]@{schema_version=1;kind='relic_editor';savefile=$save;sha256=$hashes} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'package.json') -Encoding utf8
[ordered]@{path=$out} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'local/runtime-probe-package.json') -Encoding utf8
Write-Output $out
