param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$ProjectRoot='E:\Codex\Project\黑环mod'
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$local=[IO.Path]::GetFullPath((Join-Path $root 'local')) + [IO.Path]::DirectorySeparatorChar
$output=[IO.Path]::GetFullPath($OutputDirectory)
if (-not $output.StartsWith($local,[StringComparison]::OrdinalIgnoreCase)) { throw 'Output must be under project/local' }
if (Test-Path -LiteralPath $output) { throw 'Output directory already exists; preserve prior evidence' }
$plan=Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
if ($plan.schema_version -ne 1 -or @($plan.changes).Count -eq 0) { throw 'Invalid manifest' }
$source=Join-Path $root 'local\inputs\regulation.bin'
if ((Get-FileHash -LiteralPath $source).Hash -ne $plan.source_sha256) { throw 'Source hash mismatch' }
$lib=Join-Path $root 'local\tools\Smithbox-2.2.6'
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
Add-Type -ReferencedAssemblies @((Join-Path $lib 'Andre.SoulsFormats.dll'),'System.Collections','System.Runtime','System.Collections.NonGeneric') -TypeDefinition @'
using System;
using System.Collections;
using System.Collections.Generic;
using SoulsFormats;
public static class NrePatchDiff {
  public static string[] Compare(PARAM a, PARAM b, string name) {
    var changes=new List<string>();
    if(a.Rows.Count!=b.Rows.Count) throw new Exception("Row count changed");
    for(int i=0;i<a.Rows.Count;i++){
      var x=a.Rows[i];var y=b.Rows[i];
      if(x.ID!=y.ID||x.Name!=y.Name||x.Cells.Count!=y.Cells.Count) throw new Exception("Row structure changed");
      for(int j=0;j<x.Cells.Count;j++){
        var c=x.Cells[j];var d=y.Cells[j];
        if(c.Def.InternalName!=d.Def.InternalName) throw new Exception("Schema changed");
        if(!StructuralComparisons.StructuralEqualityComparer.Equals(c.Value,d.Value))
          changes.Add(name+"|"+x.ID+(name=="ItemTableParam" ? "@"+i : "")+"|"+c.Def.InternalName+"|"+Convert.ToString(c.Value,System.Globalization.CultureInfo.InvariantCulture)+"|"+Convert.ToString(d.Value,System.Globalization.CultureInfo.InvariantCulture));
      }
    }
    return changes.ToArray();
  }
}
'@
$bundle=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($source)
if ($bundle.Version -ne $plan.regulation_internal_version) { throw 'Version mismatch' }
$originals=@{}; $defs=@{}; $entries=@{}; $expected=@{}
foreach($change in $plan.changes){
    # This minimal builder is deliberately restricted to integer field edits.
    $name=[string]$change.table
    if ($name -notin @('EquipParamAntique','ShopLineupParam','ItemTableParam','ItemLotParam_enemy')) { throw "Table not allowed: $name" }
    $identity=[string]$change.row_id
    if($name -eq 'ItemTableParam'){
        if($change.field -ne 'chanceWeight' -or $null -eq $change.row_ordinal -or [int]$change.row_ordinal -lt 0 -or
           $null -eq $change.guard.itemId -or $null -eq $change.guard.itemCategory -or
           [long]$change.after -lt 0 -or [long]$change.after -gt 65535){throw 'Invalid weighted pool edit'}
        $identity += "@$($change.row_ordinal)"
    }
    if($name -eq 'ItemLotParam_enemy'){
        if($change.field -notmatch '^lotItemId0[1-8]$' -or $null -eq $change.guard -or
           @($change.guard.PSObject.Properties).Count -lt 2){throw 'Invalid reward route edit'}
    }
    $key="$name|$identity|$($change.field)"
    if($expected.ContainsKey($key)){throw "Duplicate change: $key"}
    if([long]$change.before -eq [long]$change.after){throw "No-op change: $key"}
    $expected[$key]="$key|$($change.before)|$($change.after)"
    if(-not $entries.ContainsKey($name)){
        $match=@($bundle.Files | Where-Object { $_.Name.EndsWith("\$name.param") })
        if($match.Count -ne 1){throw "Missing table: $name"}
        $entries[$name]=$match[0]
        $defName = if($name -eq 'ItemLotParam_enemy'){'ItemLotParam'}else{$name}
        $def=[SoulsFormats.PARAMDEF]::XmlDeserialize((Join-Path $lib "Assets\PARAM\NR\Defs\$defName.xml"),$true)
        $defs[$name]=$def.GetFilteredParamdefForRegulationVersion([uint64]$bundle.Version)
        $originals[$name]=[SoulsFormats.PARAM]::Read($match[0].Bytes)
        $originals[$name].ApplyParamdef($defs[$name])
    }
}
foreach($name in $entries.Keys){
    $param=[SoulsFormats.PARAM]::Read($entries[$name].Bytes)
    $param.ApplyParamdef($defs[$name])
    foreach($change in @($plan.changes | Where-Object table -eq $name)){
        if($name -eq 'ItemTableParam'){
            if([int]$change.row_ordinal -ge $param.Rows.Count){throw 'Ordinal outside table'}
            $rows=@($param.Rows[[int]$change.row_ordinal])
            if($rows[0].ID -ne $change.row_id){throw 'Pool ordinal/ID mismatch'}
        }else{$rows=@($param.Rows | Where-Object ID -eq $change.row_id)}
        if($rows.Count -ne 1){throw 'Row must resolve uniquely'}
        if($null -ne $change.guard){
            foreach($guard in $change.guard.PSObject.Properties){
                $guardCells=@($rows[0].Cells | Where-Object {$_.Def.InternalName -eq $guard.Name})
                if($guardCells.Count -ne 1 -or [long]$guardCells[0].Value -ne [long]$guard.Value){throw "Guard mismatch: $name/$($change.row_id)/$($guard.Name)"}
            }
        }
        $cells=@($rows[0].Cells | Where-Object { $_.Def.InternalName -eq $change.field })
        if($cells.Count -ne 1 -or [long]$cells[0].Value -ne [long]$change.before){throw "Original value mismatch: $name/$($change.row_id)/$($change.field)"}
        $cells[0].Value=[Convert]::ChangeType($change.after,$cells[0].Value.GetType())
    }
    $entries[$name].Bytes=[Memory[byte]]::new([byte[]]$param.Write())
}
New-Item -ItemType Directory -Path $output | Out-Null
$candidate=Join-Path $output 'regulation.unverified.bin'
[SoulsFormats.SFUtil]::EncryptNightreignRegulation($candidate,$bundle,$bundle.Compression)
$roundtrip=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($candidate)
$originalBundle=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($source)
if($roundtrip.Files.Count -ne $originalBundle.Files.Count){throw 'Container shape changed'}
$actual=@()
for($i=0;$i -lt $roundtrip.Files.Count;$i++){
    $a=$originalBundle.Files[$i];$b=$roundtrip.Files[$i]
    if($a.Name -ne $b.Name -or $a.ID -ne $b.ID){throw 'Container identity changed'}
    $name=[IO.Path]::GetFileNameWithoutExtension($a.Name)
    if($entries.ContainsKey($name)){
        $param=[SoulsFormats.PARAM]::Read($b.Bytes);$param.ApplyParamdef($defs[$name])
        $actual+= [NrePatchDiff]::Compare($originals[$name],$param,$name)
    } else {
        if([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($a.Bytes.ToArray())) -ne [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($b.Bytes.ToArray()))){throw "Unexpected changed resource $($a.Name)"}
    }
}
if(@(Compare-Object @($expected.Values | Sort-Object) @($actual | Sort-Object)).Count){throw 'Actual diff differs from manifest'}
$final=Join-Path $output 'regulation.bin'
Move-Item -LiteralPath $candidate -Destination $final
[ordered]@{status='BUILD_VERIFIED_GAME_PENDING';source_sha256=$plan.source_sha256;output_sha256=(Get-FileHash -LiteralPath $final).Hash;changes=$actual;other_resources_unchanged=$true;manifest_sha256=(Get-FileHash -LiteralPath $Manifest).Hash} |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'build-report.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $output 'build-report.json')
