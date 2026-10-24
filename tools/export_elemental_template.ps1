param([string]$ProjectRoot='E:\Codex\Project\黑环mod')
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$lib=Join-Path $root 'local/tools/Smithbox-2.2.6'
[Environment]::CurrentDirectory=$lib;Set-Location -LiteralPath $lib
foreach($n in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){[Reflection.Assembly]::LoadFrom((Join-Path $lib $n))|Out-Null}
$source=Join-Path $root 'local/inputs/regulation.bin'
$b=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($source)
if($b.Version -ne '10350000'){throw 'Unsupported source regulation'}
Add-Type -ReferencedAssemblies @((Join-Path $lib 'Andre.SoulsFormats.dll'),'System.Collections','System.Runtime') -TypeDefinition @'
using System;using System.Collections.Generic;using SoulsFormats;
public static class ElementExport {
 public static Dictionary<string,object>[] Rows(PARAM p){
 var rows=new List<Dictionary<string,object>>();
 foreach(var r in p.Rows){var cells=new Dictionary<string,object>();foreach(var c in r.Cells){if(!c.Def.InternalType.StartsWith("dummy"))cells[c.Def.InternalName]=c.Value;}
 rows.Add(new Dictionary<string,object>{{"id",r.ID},{"fields",cells}});}
 return rows.ToArray();}
}
'@
$out=Join-Path $root 'local/elemental-combo';[void][IO.Directory]::CreateDirectory($out)
$meta=@{regulation_sha256=(Get-FileHash $source).Hash;version=$b.Version;tables=@()}
foreach($name in 'MixcraftMagicParam','Magic','Bullet','SpEffectParam','AtkParam_Pc','AttachEffectParam','BehaviorParam_PC','CharaInitParam','SpEffectSetParam'){
 $file=@($b.Files|Where-Object {$_.Name.EndsWith("\$name.param")});if($file.Count -ne 1){throw "Missing table $name"}
 $defName=switch($name){'AtkParam_Pc' {'AtkParam'} 'BehaviorParam_PC' {'BehaviorParam'} default {$name}}
 $def=[SoulsFormats.PARAMDEF]::XmlDeserialize((Join-Path $lib "Assets/PARAM/NR/Defs/$defName.xml"),$true)
 $p=[SoulsFormats.PARAM]::Read($file[0].Bytes);$p.ApplyParamdef($def.GetFilteredParamdefForRegulationVersion([uint64]$b.Version))
 $rows=[ElementExport]::Rows($p)
 ConvertTo-Json -InputObject $rows -Depth 6 -Compress | Set-Content -LiteralPath (Join-Path $out "$name.json") -Encoding utf8
 $meta.tables+=@{name=$name;rows=$p.Rows.Count};Write-Output "$name $($p.Rows.Count)"
}
$meta|ConvertTo-Json -Depth 4|Set-Content (Join-Path $out 'sources.json') -Encoding utf8
