param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$ProjectRoot='E:\Codex\Project\黑环mod'
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$local=[IO.Path]::GetFullPath((Join-Path $root 'local'))+[IO.Path]::DirectorySeparatorChar
$output=[IO.Path]::GetFullPath($OutputDirectory)
if(-not $output.StartsWith($local,[StringComparison]::OrdinalIgnoreCase)){throw 'Output outside project/local'}
if(Test-Path -LiteralPath $output){throw 'Output already exists'}
$plan=Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
$pinned='876A3CA279A4561D0C69F81FE5E510C75C59AB9A8A201694F8CF4A42C91E0268'
if($plan.schema_version -ne 2 -or $plan.source_sha256 -ne $pinned -or @($plan.additions).Count -ne 32){throw 'Unsupported private-pool manifest'}
$source=Join-Path $root 'local\inputs\regulation.bin'
if((Get-FileHash -LiteralPath $source).Hash -ne $pinned){throw 'Original hash mismatch'}
$lib=Join-Path $root 'local\tools\Smithbox-2.2.6'
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
Add-Type -ReferencedAssemblies @((Join-Path $lib 'Andre.SoulsFormats.dll'),'System.Collections','System.Runtime','System.Collections.NonGeneric') -TypeDefinition @'
using System;
using System.Collections;
using System.Collections.Generic;
using SoulsFormats;
public static class NrePoolAudit {
 public static void EqualRow(PARAM.Row a,PARAM.Row b) {
  if(a.ID!=b.ID||a.Name!=b.Name||a.Cells.Count!=b.Cells.Count)throw new Exception("Row structure mismatch");
  for(int i=0;i<a.Cells.Count;i++)
   if(a.Cells[i].Def.InternalName!=b.Cells[i].Def.InternalName||
      !StructuralComparisons.StructuralEqualityComparer.Equals(a.Cells[i].Value,b.Cells[i].Value))
    throw new Exception("Unexpected cell at row "+a.ID+" field "+a.Cells[i].Def.InternalName);
 }
 public static void Equal(PARAM a,PARAM b) {
  if(a.Rows.Count!=b.Rows.Count)throw new Exception("Row count mismatch");
  for(int i=0;i<a.Rows.Count;i++)EqualRow(a.Rows[i],b.Rows[i]);
 }
 public static long V(PARAM.Row r,string name) {
  foreach(var c in r.Cells)if(c.Def.InternalName==name)return Convert.ToInt64(c.Value);
  throw new Exception("Missing field "+name);
 }
 public static void Graph(PARAM p,int first,int originalCount) {
  var groups=new Dictionary<int,List<PARAM.Row>>();
  for(int i=originalCount;i<p.Rows.Count;i++){
   var row=p.Rows[i];
   if(row.ID<first||row.ID>=first+9)throw new Exception("Outside NRE pool allocation");
   if(!groups.ContainsKey(row.ID))groups[row.ID]=new List<PARAM.Row>();
   groups[row.ID].Add(row);
  }
  if(groups.Count!=9)throw new Exception("Expected nine private pools");
  var visiting=new HashSet<int>();var done=new HashSet<int>();
  foreach(var id in groups.Keys)Visit(id,groups,visiting,done);
 }
 static void Visit(int id,Dictionary<int,List<PARAM.Row>> groups,HashSet<int> active,HashSet<int> done) {
  if(active.Contains(id))throw new Exception("Reward pool cycle");
  if(done.Contains(id))return;
  if(!groups.ContainsKey(id))throw new Exception("Missing private pool target");
  active.Add(id);long sum=0;
  foreach(var row in groups[id]){
   long weight=V(row,"chanceWeight");sum+=weight;
   long cat=V(row,"itemCategory");
   if(cat==7)Visit((int)V(row,"itemId"),groups,active,done);
   else if(cat!=1)throw new Exception("Unsupported new pool entry");
  }
  if(sum<=0)throw new Exception("Empty pool");
  active.Remove(id);done.Add(id);
 }
}
'@
$bundle=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($source)
if($bundle.Version -ne $plan.regulation_internal_version){throw 'Regulation version mismatch'}
$defs=@{};$params=@{};$entries=@{};$original=@{}
foreach($name in 'ItemTableParam','ItemLotParam_enemy'){
    $matches=@($bundle.Files | Where-Object {$_.Name.EndsWith("\$name.param")})
    if($matches.Count -ne 1){throw "Missing table $name"}
    $entries[$name]=$matches[0]
    $defName=if($name -eq 'ItemLotParam_enemy'){'ItemLotParam'}else{$name}
    $def=[SoulsFormats.PARAMDEF]::XmlDeserialize((Join-Path $lib "Assets\PARAM\NR\Defs\$defName.xml"),$true)
    $defs[$name]=$def.GetFilteredParamdefForRegulationVersion([uint64]$bundle.Version)
    $params[$name]=[SoulsFormats.PARAM]::Read($matches[0].Bytes)
    $params[$name].ApplyParamdef($defs[$name])
    $original[$name]=[SoulsFormats.PARAM]::Read($matches[0].Bytes)
    $original[$name].ApplyParamdef($defs[$name])
}
function Set-IntegerCell($row,$field,$value){
    if($null -eq $value -or [decimal]$value -ne [long]$value){throw 'Non-integral patch value'}
    $cells=@($row.Cells | Where-Object {$_.Def.InternalName -eq $field})
    if($cells.Count -ne 1){throw "Field not unique: $field"}
    $cells[0].Value=[Convert]::ChangeType($value,$cells[0].Value.GetType())
}
function Check-Guard($row,$guard){
    if($null -eq $guard){throw 'Missing guard'}
    foreach($property in $guard.PSObject.Properties){
        if([NrePoolAudit]::V($row,$property.Name) -ne [long]$property.Value){throw "Guard mismatch: $($property.Name)"}
    }
}
$table=$params['ItemTableParam'];$originalCount=$table.Rows.Count
$allocated=[Collections.Generic.HashSet[int]]::new()
foreach($row in $table.Rows){
    if($row.ID -ge 1900100000){throw 'Cannot safely append private allocation after original rows'}
}
$lastId=1900100000
foreach($addition in $plan.additions){
    if($addition.table -ne 'ItemTableParam' -or $addition.row_id -lt 1900100000 -or $addition.row_id -gt 1900100008){throw 'Invalid private row ID'}
    if($addition.row_id -lt $lastId){throw 'New rows must retain sorted group order'}
    $lastId=[int]$addition.row_id
    if($null -eq $addition.source_ordinal -or $addition.source_ordinal -lt 0 -or $addition.source_ordinal -ge $originalCount){throw 'Invalid template ordinal'}
    $template=$original['ItemTableParam'].Rows[[int]$addition.source_ordinal]
    if($template.ID -ne $addition.source_row_id){throw 'Template ordinal/ID mismatch'}
    foreach($required in 'itemId','itemCategory','quantity','onlyForClass','eventFlagId','disableParam_NT','unknown_6','unknown_7'){
        if($null -eq $addition.guard.$required){throw "Missing template guard: $required"}
    }
    Check-Guard $template $addition.guard
    $row=[SoulsFormats.PARAM+Row]::new($template)
    $row.ID=[int]$addition.row_id
    foreach($property in $addition.overrides.PSObject.Properties){
        if($property.Name -notin @('itemId','chanceWeight')){throw 'Disallowed clone override'}
        if($property.Name -eq 'itemId' -and [NrePoolAudit]::V($template,'itemCategory') -ne 7){throw 'Cannot change copied good identity'}
        Set-IntegerCell $row $property.Name $property.Value
    }
    if([NrePoolAudit]::V($row,'chanceWeight') -lt 0){throw 'Negative weight'}
    $table.Rows.Add($row);$allocated.Add($row.ID) | Out-Null
}
[NrePoolAudit]::Graph($table,1900100000,$originalCount)
for($i=0;$i -lt $originalCount;$i++){[NrePoolAudit]::EqualRow($original['ItemTableParam'].Rows[$i],$table.Rows[$i])}
$lot=$params['ItemLotParam_enemy'];$keys=@{};$changes=@()
if(@($plan.changes).Count -ne 8){throw 'Expected eight fort route changes'}
foreach($change in $plan.changes){
    $key="$($change.row_id)|$($change.field)"
    if($keys.ContainsKey($key)){throw 'Duplicate route edit'};$keys[$key]=$true
    if($change.table -ne 'ItemLotParam_enemy' -or $change.row_id -notin @(6000050,6000051,6000052) -or $change.field -notmatch '^lotItemId0[1-8]$'){throw 'Disallowed route'}
    $rows=@($lot.Rows | Where-Object ID -eq $change.row_id)
    if($rows.Count -ne 1){throw 'Ambiguous route row'}
    $row=$rows[0];$suffix=$change.field.Substring($change.field.Length-2)
    if([NrePoolAudit]::V($row,"lotItemCategory$suffix") -ne 7 -or [NrePoolAudit]::V($row,"lotItemBasePoint$suffix") -le 0){throw 'Not an active native pool route'}
    Check-Guard $row $change.guard
    if([NrePoolAudit]::V($row,$change.field) -ne $change.before){throw 'Route original value mismatch'}
    $expectedRoot=1900100000+([int]$change.row_id-6000050)*3
    if($change.after -ne $expectedRoot){throw 'Route must select its family root'}
    Set-IntegerCell $row $change.field $change.after
    $changes += "ItemLotParam_enemy|$key|$($change.before)|$($change.after)"
}
foreach($name in $entries.Keys){$entries[$name].Bytes=[Memory[byte]]::new([byte[]]$params[$name].Write())}
New-Item -ItemType Directory -Path $output | Out-Null
$candidate=Join-Path $output 'regulation.unverified.bin'
[SoulsFormats.SFUtil]::EncryptNightreignRegulation($candidate,$bundle,$bundle.Compression)
$decoded=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($candidate)
$baseline=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($source)
if($decoded.Files.Count -ne $baseline.Files.Count){throw 'Resource count changed'}
for($i=0;$i -lt $decoded.Files.Count;$i++){
    $a=$baseline.Files[$i];$b=$decoded.Files[$i]
    if($a.ID -ne $b.ID -or $a.Name -ne $b.Name){throw 'Resource identity changed'}
    $name=[IO.Path]::GetFileNameWithoutExtension($a.Name)
    if($params.ContainsKey($name)){
        $readback=[SoulsFormats.PARAM]::Read($b.Bytes);$readback.ApplyParamdef($defs[$name])
        [NrePoolAudit]::Equal($params[$name],$readback)
    }else{
        if([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($a.Bytes.ToArray())) -ne
           [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($b.Bytes.ToArray()))){throw "Unexpected resource change $name"}
    }
}
$final=Join-Path $output 'regulation.bin'
Move-Item -LiteralPath $candidate -Destination $final
[ordered]@{status='BUILD_VERIFIED_GAME_PENDING';source_sha256=$pinned;
    output_sha256=(Get-FileHash -LiteralPath $final).Hash;changes=$changes;
    new_rows=@($plan.additions).Count;private_pool_count=$allocated.Count;
    original_item_table_rows_unchanged=$true;other_resources_unchanged=$true;
    nested_graph_acyclic=$true;manifest_sha256=(Get-FileHash -LiteralPath $Manifest).Hash} |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'build-report.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $output 'build-report.json')
