param(
    [Parameter(Mandatory=$true)][string]$Plan,
    [Parameter(Mandatory=$true)][string]$RewardBase,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$ProjectRoot='E:\Codex\Project\黑环mod'
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$out=[IO.Path]::GetFullPath($OutputDirectory)
$local=[IO.Path]::GetFullPath((Join-Path $root 'local'))+[IO.Path]::DirectorySeparatorChar
if(-not $out.StartsWith($local,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)){throw 'Unsafe or existing output'}
$p=Get-Content -LiteralPath $Plan -Raw | ConvertFrom-Json
$source=Join-Path $root 'local/inputs/regulation.bin'
$pin='876A3CA279A4561D0C69F81FE5E510C75C59AB9A8A201694F8CF4A42C91E0268'
if($p.source_sha256 -ne $pin -or (Get-FileHash -LiteralPath $source).Hash -ne $pin -or
   (Get-FileHash -LiteralPath $RewardBase).Hash -ne $p.reward_sha256){throw 'Input hash mismatch'}
if($p.schema_version -ne 1 -or $p.price -ne 1 -or $p.currency_cost_type -ne 4 -or
   @($p.products).Count -ne 83 -or $p.state_first -ne 200000 -or $p.state_end -gt 300000){throw 'Unsupported editor plan'}
$lib=Join-Path $root 'local/tools/Smithbox-2.2.6'
[Environment]::CurrentDirectory=$lib
Set-Location -LiteralPath $lib
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
Add-Type -ReferencedAssemblies @((Join-Path $lib 'Andre.SoulsFormats.dll'),'System.Collections','System.Runtime','System.Collections.NonGeneric','System.Linq') -TypeDefinition @'
using System;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using SoulsFormats;
public static class NreEditorNative {
 public static byte[] Num(int n) {return new byte[]{0x82}.Concat(BitConverter.GetBytes(n)).Concat(new byte[]{0xa1}).ToArray();}
 public static ESD.CommandCall Copy(ESD.CommandCall c) {
  return new ESD.CommandCall(c.CommandBank,c.CommandID,c.Arguments.Select(a=>(byte[])a.Clone()).ToArray());
 }
 public static ESD.Condition Copy(ESD.Condition c) {
  var n=new ESD.Condition();n.TargetState=c.TargetState;n.Evaluator=(byte[])c.Evaluator.Clone();
  foreach(var x in c.PassCommands)n.PassCommands.Add(Copy(x));
  foreach(var x in c.Subconditions)n.Subconditions.Add(Copy(x));return n;
 }
 public static ESD.State Copy(ESD.State s) {
  var n=new ESD.State();
  foreach(var c in s.EntryCommands)n.EntryCommands.Add(Copy(c));
  foreach(var c in s.ExitCommands)n.ExitCommands.Add(Copy(c));
  foreach(var c in s.WhileCommands)n.WhileCommands.Add(Copy(c));
  foreach(var c in s.Conditions)n.Conditions.Add(Copy(c));return n;
 }
 public static ESD.Condition Go(long id){return new ESD.Condition(id,new byte[]{0x41,0xa1});}
 public static void Page(Dictionary<long,ESD.State> states,long id,long back,int[] texts,long[] targets,
  ESD.State clear,ESD.CommandCall item,ESD.State show,ESD.Condition choice) {
  if(texts.Length!=targets.Length||texts.Length<1||texts.Length>10)throw new Exception("Invalid menu entries");
  var a=Copy(clear);a.Conditions.Clear();a.Conditions.Add(Go(id+1));states.Add(id,a);
  var b=new ESD.State();var dispatch=new ESD.State();
  for(int i=0;i<texts.Length;i++){
   var c=Copy(item);c.Arguments[0]=Num(i+1);c.Arguments[1]=Num(texts[i]);c.Arguments[3]=Num(i+1);b.EntryCommands.Add(c);
   var condition=Copy(choice);
   condition.Evaluator=new byte[]{0x57,0x84,0xa7}.Concat(Num(i+1).Take(5)).Concat(new byte[]{0x95,0xa1}).ToArray();
   condition.TargetState=targets[i];dispatch.Conditions.Add(condition);
  }
  b.Conditions.Add(Go(id+2));states.Add(id+1,b);
  var modal=Copy(show);modal.Conditions[0].TargetState=id+3;modal.Conditions[1].TargetState=back;states.Add(id+2,modal);
  dispatch.Conditions.Add(Go(back));states.Add(id+3,dispatch);
 }
 public static void Shop(Dictionary<long,ESD.State> states,long id,int shopId,long back,ESD.State original) {
  var n=Copy(original);n.EntryCommands[0].Arguments[0]=Num(shopId);n.EntryCommands[0].Arguments[1]=Num(shopId);
  n.Conditions[0].TargetState=back;states.Add(id,n);
 }
 public static void Equal(PARAM.Row a,PARAM.Row b) {
  if(a.ID!=b.ID||a.Name!=b.Name||a.Cells.Count!=b.Cells.Count)throw new Exception("Original row structure changed");
  for(int i=0;i<a.Cells.Count;i++)
   if(a.Cells[i].Def.InternalName!=b.Cells[i].Def.InternalName||
      !StructuralComparisons.StructuralEqualityComparer.Equals(a.Cells[i].Value,b.Cells[i].Value))
    throw new Exception("Original row cell changed");
 }
 public static void Prefix(PARAM a,PARAM b) {
  if(b.Rows.Count<a.Rows.Count)throw new Exception("Removed original rows");
  for(int i=0;i<a.Rows.Count;i++)Equal(a.Rows[i],b.Rows[i]);
 }
 public static long V(PARAM.Row row,string name){
  foreach(var c in row.Cells)if(c.Def.InternalName==name)return Convert.ToInt64(c.Value);
  throw new Exception("Missing integer field");
 }
 public static void Set(PARAM.Row row,string name,long value){
  foreach(var c in row.Cells)if(c.Def.InternalName==name){c.Value=Convert.ChangeType(value,c.Value.GetType());return;}
  throw new Exception("Missing integer field");
 }
 public static void Targets(ESD esd){
  foreach(var group in esd.StateGroups.Values)foreach(var s in group.Values)Check(s.Conditions,group);
 }
 static void Check(List<ESD.Condition> list,Dictionary<long,ESD.State> group){
  foreach(var c in list){
   if(c.TargetState.HasValue&&!group.ContainsKey(c.TargetState.Value))throw new Exception("Dangling ESD target");
   Check(c.Subconditions,group);
  }
 }
 public static void NoBusyCycle(Dictionary<long,ESD.State> group,long first,long end,HashSet<long> modal){
  var done=new HashSet<long>();var active=new HashSet<long>();
  for(long id=first;id<end;id++)Visit(id,group,first,end,modal,done,active);
 }
 static void Visit(long id,Dictionary<long,ESD.State> g,long first,long end,HashSet<long> modal,HashSet<long> done,HashSet<long> active){
  if(id<first||id>=end||modal.Contains(id)||done.Contains(id))return;
  if(!active.Add(id))throw new Exception("Cycle without native modal wait");
  foreach(var c in g[id].Conditions)if(c.TargetState.HasValue)Visit(c.TargetState.Value,g,first,end,modal,done,active);
  active.Remove(id);done.Add(id);
 }
}
'@
function Hash($bytes){return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([byte[]]$bytes))}
function Bundle-Equal($a,$b){
    if($a.Version -ne $b.Version -or $a.Files.Count -ne $b.Files.Count){throw 'Binder structure changed'}
    for($i=0;$i -lt $a.Files.Count;$i++){
        $x=$a.Files[$i];$y=$b.Files[$i]
        if($x.ID -ne $y.ID -or $x.Name -ne $y.Name -or $x.Flags -ne $y.Flags -or
           (Hash $x.Bytes.ToArray()) -ne (Hash $y.Bytes.ToArray())){throw 'Binder roundtrip mismatch'}
    }
}
function Table($bundle,$name){
    $entry=@($bundle.Files | Where-Object {$_.Name.EndsWith("\$name.param")})
    if($entry.Count -ne 1){throw 'Missing table'}
    $def=[SoulsFormats.PARAMDEF]::XmlDeserialize((Join-Path $lib "Assets/PARAM/NR/Defs/$name.xml"),$true)
    $table=[SoulsFormats.PARAM]::Read($entry[0].Bytes)
    $table.ApplyParamdef($def.GetFilteredParamdefForRegulationVersion([uint64]$bundle.Version))
    return @{table=$table;entry=$entry[0]}
}
function Guard($row,$guard){
    foreach($property in $guard.PSObject.Properties){
        if([NreEditorNative]::V($row,$property.Name) -ne $property.Value){throw 'Native template guard changed'}
    }
}
Write-Output 'Building deterministic relic products'
$base=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($RewardBase)
$original=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($source)
if($base.Version -ne '10350000'){throw 'Unsupported regulation version'}
$ant=Table $base 'EquipParamAntique';$shop=Table $base 'ShopLineupParam'
$oldAnt=Table $original 'EquipParamAntique';$oldShop=Table $original 'ShopLineupParam'
if((Hash $ant.entry.Bytes.ToArray()) -ne (Hash $oldAnt.entry.Bytes.ToArray()) -or
   (Hash $shop.entry.Bytes.ToArray()) -ne (Hash $oldShop.entry.Bytes.ToArray())){throw 'Reward input already modifies relic/shop tables'}
$pool=Table $original 'AttachEffectTableParam'
$pools=@{};foreach($row in $pool.table.Rows){if(-not $pools.ContainsKey($row.ID)){$pools[$row.ID]=[Collections.Generic.List[object]]::new()};$pools[$row.ID].Add($row)}
$templates=@{};foreach($row in $ant.table.Rows){$templates[$row.ID]=$row;if($row.ID -ge 9000000){throw 'Relic allocation unsafe'}}
$shopTemplate=@($shop.table.Rows | Where-Object ID -eq $p.shop_template_id)
if($shopTemplate.Count -ne 1){throw 'Missing shop template'}
Guard $shopTemplate[0] $p.shop_template_guard
foreach($row in $shop.table.Rows){if($row.ID -ge 1900200000){throw 'Shop allocation unsafe'}}
$counter=0
foreach($product in $p.products){
    if($product.relic_id -ne (9000000+$counter) -or $product.shop_id -ne (1900200000+$counter)){throw 'Invalid product allocation'}
    $template=$templates[[int]$product.template_id]
    if($null -eq $template){throw 'Missing relic template'}
    Guard $template $product.template_guard
    $row=[SoulsFormats.PARAM+Row]::new($template);$row.ID=[int]$product.relic_id
    if(@($product.relic_overrides.PSObject.Properties).Count -ne 6){throw 'Wrong relic override count'}
    for($slot=1;$slot -le 3;$slot++){
        foreach($negative in @($false,$true)){
            $field=if($negative){"attachEffectTableId_curse$slot"}else{"attachEffectTableId_$slot"}
            $effect=if($negative){$product.curses[$slot-1]}else{$product.effects[$slot-1]}
            $value=$product.relic_overrides.$field
            if($null -eq $value){throw 'Missing slot override'}
            $nativePool=[int][NreEditorNative]::V($template,$field)
            if($null -eq $effect){
                if($value -ne -1 -or $nativePool -ne -1){throw 'Curse removed from required slot'}
            }else{
                $fixed=@($pools[[int]$value])
                if($fixed.Count -ne 1 -or [NreEditorNative]::V($fixed[0],'attachEffectId') -ne $effect -or
                   [NreEditorNative]::V($fixed[0],'chanceWeight') -le 0){throw 'Non-deterministic effect pool'}
                $allowed=@($pools[$nativePool] | Where-Object {
                    [NreEditorNative]::V($_,'attachEffectId') -eq $effect -and
                    [NreEditorNative]::V($_,'chanceWeight') -gt 0 -and
                    ([NreEditorNative]::V($_,'chanceWeight_dlc') -eq -1 -or [NreEditorNative]::V($_,'chanceWeight_dlc') -gt 0)
                })
                if(-not $allowed.Count){throw 'Effect not allowed by native slot'}
            }
            [NreEditorNative]::Set($row,$field,[long]$value)
        }
    }
    $ant.table.Rows.Add($row)
    $item=[SoulsFormats.PARAM+Row]::new($shopTemplate[0]);$item.ID=[int]$product.shop_id
    foreach($pair in @{equipId=$product.relic_id;value=1;costType=4;eventFlag_forStock=0;eventFlag_forRelease=0;sellQuantity=-1;setNum=1}.GetEnumerator()){
        [NreEditorNative]::Set($item,$pair.Key,[long]$pair.Value)
    }
    $shop.table.Rows.Add($item);$counter++
}
[NreEditorNative]::Prefix($oldAnt.table,$ant.table)
[NreEditorNative]::Prefix($oldShop.table,$shop.table)
$ant.entry.Bytes=[Memory[byte]]::new([byte[]]$ant.table.Write())
$shop.entry.Bytes=[Memory[byte]]::new([byte[]]$shop.table.Write())
[IO.Directory]::CreateDirectory($out) | Out-Null
$reg=Join-Path $out 'regulation.bin'
[SoulsFormats.SFUtil]::EncryptNightreignRegulation($reg,$base,$base.Compression)
Bundle-Equal $base ([SoulsFormats.SFUtil]::DecryptNightreignRegulation($reg))
Write-Output 'Building native editor pages'
$pins=@{
 'script/talk/m10_00_00_00.talkesdbnd.dcx'='43D5005F1934A37121CA2589C58684E73964F2440B1D13BB79443AC689796CD1'
 'msg/zhocn/menu_dlc01.msgbnd.dcx'='A56F88BEBA7D8ABA36D2D436E9EF2E08E28A2189EEE87075F792B39B774A9E52'
 'msg/engus/menu_dlc01.msgbnd.dcx'='E33F1C338878DA423D95CF54589072D99425F2A92C10603E5C93BDA9323184DB'
}
$resourceRoot=Join-Path $root 'local/native-menu/original'
foreach($path in $pins.Keys){if((Get-FileHash -LiteralPath (Join-Path $resourceRoot $path)).Hash -ne $pins[$path]){throw 'Original UI resource changed'}}
$talk='script/talk/m10_00_00_00.talkesdbnd.dcx'
$bundle=[SoulsFormats.BND4]::Read((Join-Path $resourceRoot $talk))
$entry=@($bundle.Files | Where-Object Name -match '\\t605001000\.esd$')
if($entry.Count -ne 1){throw 'Merchant not unique'}
$esd=[SoulsFormats.ESD]::Read($entry[0].Bytes)
$oldEsd=[SoulsFormats.ESD]::Read($entry[0].Bytes)
$group=$esd.StateGroups[[long]2147483643];$menu=$esd.StateGroups[[long]2147483644]
$shopState=[NreEditorNative]::Copy($group[[long]1])
if($shopState.EntryCommands[0].CommandID -ne 155 -or
   [Convert]::ToHexString($shopState.EntryCommands[0].Arguments[0]) -ne '8210270000A1'){throw 'Shop template changed'}
for($id=[long]$p.state_first;$id -lt $p.state_end;$id++){if($group.ContainsKey($id)){throw 'Editor state collision'}}
$modal=[Collections.Generic.HashSet[long]]::new()
foreach($page in $p.pages){
    if($null -ne $page.editor -and @($page.entries).Count -ne 5){throw 'Editor requires five choices'}
    [NreEditorNative]::Page($group,[long]$page.state,[long]$page.back,[int[]]@($page.entries.text_id),[long[]]@($page.entries.target),
        $menu[[long]8],$menu[[long]9].EntryCommands[0],$menu[[long]10],$menu[[long]11].Conditions[0])
    $modal.Add([long]$page.state+2) | Out-Null
}
$group.Add([long]$p.original_shop_state,$shopState)
$modal.Add([long]$p.original_shop_state) | Out-Null
$productIds=[Collections.Generic.HashSet[int]]::new()
foreach($product in $p.products){$productIds.Add([int]$product.shop_id) | Out-Null}
foreach($purchase in $p.purchases){
    if(-not $productIds.Contains([int]$purchase.shop_id)){throw 'Unbound craft product'}
    [NreEditorNative]::Shop($group,[long]$purchase.state,[int]$purchase.shop_id,[long]$purchase.back,$shopState)
    $modal.Add([long]$purchase.state) | Out-Null
}
$start=[SoulsFormats.ESD+State]::new();$start.Conditions.Add([NreEditorNative]::Go([long]$p.root_state))
$group[[long]1]=$start
[NreEditorNative]::Targets($esd)
[NreEditorNative]::NoBusyCycle($group,[long]$p.state_first,[long]$p.state_end,$modal)
$probe=[SoulsFormats.ESD]::Read($esd.Write());$probeGroup=$probe.StateGroups[[long]2147483643]
for($id=[long]$p.state_first;$id -lt $p.state_end;$id++){$probeGroup.Remove($id) | Out-Null}
$probeGroup[[long]1]=$oldEsd.StateGroups[[long]2147483643][[long]1]
if((Hash $probe.Write()) -ne (Hash $oldEsd.Write())){throw 'Original ESD changed beyond entry point'}
$entry[0].Bytes=[Memory[byte]]::new([byte[]]$esd.Write())
$target=Join-Path $out $talk
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
$bundle.Write($target);Bundle-Equal $bundle ([SoulsFormats.BND4]::Read($target))
foreach($lang in 'zhocn','engus'){
    $path="msg/$lang/menu_dlc01.msgbnd.dcx"
    $bundle=[SoulsFormats.BND4]::Read((Join-Path $resourceRoot $path))
    $entry=@($bundle.Files | Where-Object Name -match '\\EventTextForTalk\.fmg$')
    if($entry.Count -ne 1){throw 'Menu text resource not unique'}
    $fmg=[SoulsFormats.FMG]::Read($entry[0].Bytes)
    $used=[Collections.Generic.HashSet[int]]::new()
    foreach($text in $fmg.Entries){$used.Add($text.ID) | Out-Null}
    foreach($text in $p.texts){
        if($text.id -lt 1900300000 -or $text.id -gt 1900309999 -or -not $used.Add([int]$text.id) -or
           [string]::IsNullOrWhiteSpace($text.$lang)){throw 'Invalid or conflicting menu text'}
        $fmg.Entries.Add([SoulsFormats.FMG+Entry]::new($fmg,[int]$text.id,[string]$text.$lang))
    }
    $entry[0].Bytes=[Memory[byte]]::new([byte[]]$fmg.Write())
    $target=Join-Path $out $path
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
    $bundle.Write($target);Bundle-Equal $bundle ([SoulsFormats.BND4]::Read($target))
}
[ordered]@{status='EDITOR_BUILT_GAME_PENDING';products=$counter;price=1;currency_cost_type=4;
    normal_editors=2;deep_editors=2;pages=@($p.pages).Count;new_states=($p.state_end-$p.state_first);
    texts_per_language=@($p.texts).Count;original_param_rows_preserved=$true;
    original_esd_restoration_verified=$true;all_resource_roundtrips_verified=$true;
    no_cycles_without_modal_wait=$true;native_slot_membership_verified=$true;
    user_difficulty_budget_enforced=$false;game_verified=$false;limitations=$p.limitations} |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $out 'editor-report.json') -Encoding utf8
Write-Output "Editor verified: products=$counter, pages=$(@($p.pages).Count)"
