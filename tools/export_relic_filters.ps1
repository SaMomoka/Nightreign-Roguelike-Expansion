param([string]$ProjectRoot='E:\Codex\Project\黑环mod')
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$lib=Join-Path $root 'local/tools/Smithbox-2.2.6'
[Environment]::CurrentDirectory=$lib
Set-Location -LiteralPath $lib
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
 [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
$inputPath=Join-Path $root 'local/inputs/regulation.bin'
$pin='876A3CA279A4561D0C69F81FE5E510C75C59AB9A8A201694F8CF4A42C91E0268'
if((Get-FileHash -LiteralPath $inputPath).Hash -ne $pin){throw 'Unverified regulation'}
$reg=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($inputPath)
$tables=[ordered]@{}
foreach($name in 'AttachEffectParam','AttachEffectFilterParam','AttachEffectFilterCategoryParam','AttachEffectFilterSubCategoryParam','EquipParamAntique'){
 $file=@($reg.Files | Where-Object {$_.Name.EndsWith("\$name.param")})[0]
 $p=[SoulsFormats.PARAM]::Read($file.Bytes)
 $def=[SoulsFormats.PARAMDEF]::XmlDeserialize((Join-Path $lib "Assets/PARAM/NR/Defs/$name.xml"),$true)
 $p.ApplyParamdef($def.GetFilteredParamdefForRegulationVersion([uint64]$reg.Version))
 $rows=@()
 foreach($row in $p.Rows){
  $values=[ordered]@{ID=$row.ID}
  foreach($cell in $row.Cells){if($cell.Value -isnot [array]){$values[$cell.Def.InternalName]=$cell.Value}}
  $rows+=$values
 }
 $tables[$name]=$rows
}
$wanted=[Collections.Generic.HashSet[int]]::new()
foreach($name in 'AttachEffectFilterCategoryParam','AttachEffectFilterSubCategoryParam'){
 foreach($row in $tables[$name]){if($row.textId -ge 0){[void]$wanted.Add([int]$row.textId)}}
}
$extraction=Get-Content (Join-Path $root 'local/native-menu/extraction.json') -Raw | ConvertFrom-Json
$languages=[ordered]@{}
$sources=@()
foreach($lang in 'zhocn','engus'){
 $values=@{}
 $rel="msg/$lang/menu_dlc01.msgbnd.dcx"
 $path=Join-Path $root "local/native-menu/original/$rel"
 $hash=(Get-FileHash -LiteralPath $path).Hash
 if(@($extraction.files | Where-Object {$_.path -eq $rel -and $_.sha256 -eq $hash}).Count -ne 1){throw 'Unverified text'}
 $sources+=@{path=$rel;sha256=$hash}
 $b=[SoulsFormats.BND4]::Read($path)
 foreach($f in $b.Files){
  if(-not $f.Name.EndsWith('.fmg')){continue}
  foreach($e in ([SoulsFormats.FMG]::Read($f.Bytes)).Entries){
   if($wanted.Contains($e.ID) -and -not [string]::IsNullOrWhiteSpace($e.Text)){
    $key=[string]$e.ID
    if($values.ContainsKey($key) -and $values[$key] -ne $e.Text){throw "Ambiguous native filter text $key"}
    $values[$key]=$e.Text
   }
  }
 }
 $languages[$lang]=$values
}
[ordered]@{schema_version=1;source_sha256=$pin;tables=$tables;languages=$languages;sources=$sources} | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $root 'local/evidence/relic-filters.json') -Encoding utf8
Write-Output 'Exported verified native filter hierarchy, effect links and color templates'
