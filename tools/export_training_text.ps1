param([string]$ProjectRoot='E:\Codex\Project\黑环mod')
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$lib=Join-Path $root 'local/tools/Smithbox-2.2.6'
[Environment]::CurrentDirectory=$lib
Set-Location -LiteralPath $lib
foreach($name in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $name)) | Out-Null
}
$extraction=Get-Content -LiteralPath (Join-Path $root 'local/native-menu/extraction.json') -Raw | ConvertFrom-Json
$result=[ordered]@{schema_version=1;sources=@();languages=[ordered]@{}}
foreach($language in 'zhocn','engus'){
    $relative="msg/$language/item_dlc01.msgbnd.dcx"
    $path=Join-Path $root "local/native-menu/original/$relative"
    $hash=(Get-FileHash -LiteralPath $path).Hash
    $source=@($extraction.files | Where-Object path -eq $relative)
    if($source.Count -ne 1 -or $source[0].sha256 -ne $hash){throw 'Unverified original text resource'}
    $result.sources+=@{path=$relative;sha256=$hash}
    $bundle=[SoulsFormats.BND4]::Read($path)
    $texts=[ordered]@{name=@{};info=@{}}
    foreach($kind in 'name','info'){
        $baseName=switch($kind){'name' {'PermanentBuffName'} 'info' {'PermanentBuffInfo'}}
        foreach($suffix in '','_dlc01'){
            $file=@($bundle.Files | Where-Object {$_.Name.EndsWith("\$baseName$suffix.fmg")})
            if($file.Count -ne 1){throw 'Missing relic text bank'}
            $fmg=[SoulsFormats.FMG]::Read($file[0].Bytes)
            foreach($entry in $fmg.Entries){
                if(-not [string]::IsNullOrWhiteSpace($entry.Text)){$texts[$kind][[string]$entry.ID]=$entry.Text}
            }
        }
    }
    $result.languages[$language]=$texts
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $root 'local/evidence/training-text.json') -Encoding utf8
Write-Output 'Exported verified ordinary/DLC goods names and descriptions'
