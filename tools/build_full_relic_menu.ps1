param([Parameter(Mandatory=$true)][string]$Package,[string]$ProjectRoot='E:\Codex\Project\黑环mod')
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$folder=(Resolve-Path -LiteralPath $Package).Path
if(-not $folder.StartsWith((Join-Path $root 'local/packages')+[IO.Path]::DirectorySeparatorChar)){throw 'Package outside project'}
$plan=Get-Content -LiteralPath (Join-Path $folder 'full-menu-plan.json') -Raw | ConvertFrom-Json
if($plan.schema_version -ne 2 -or $plan.kind -ne 'full_relic_runtime_menu' -or $plan.state_first -ne 400000 -or $plan.state_end -gt 500000){throw 'Invalid full menu plan'}
$lib=Join-Path $root 'local/tools/Smithbox-2.2.6'
[Environment]::CurrentDirectory=$lib
Set-Location -LiteralPath $lib
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
Add-Type -ReferencedAssemblies @((Join-Path $lib 'Andre.SoulsFormats.dll'),'System.Collections','System.Runtime','System.Linq') -TypeDefinition @'
using System;
using System.Linq;
using System.Collections.Generic;
using SoulsFormats;
public static class NreFull {
 public static ESD.CommandCall Copy(ESD.CommandCall c){return new ESD.CommandCall(c.CommandBank,c.CommandID,c.Arguments.Select(a=>(byte[])a.Clone()).ToArray());}
 public static ESD.Condition Copy(ESD.Condition c){
  var n=new ESD.Condition();n.TargetState=c.TargetState;n.Evaluator=(byte[])c.Evaluator.Clone();
  foreach(var p in c.PassCommands)n.PassCommands.Add(Copy(p));
  foreach(var p in c.Subconditions)n.Subconditions.Add(Copy(p));return n;
 }
 public static void Set(PARAM.Row r,string field,int value){
  foreach(var c in r.Cells)if(c.Def.InternalName==field){c.Value=Convert.ChangeType(value,c.Value.GetType());return;}
  throw new Exception("Missing param field");
 }
 public static int Get(PARAM.Row r,string field){
  foreach(var c in r.Cells)if(c.Def.InternalName==field)return Convert.ToInt32(c.Value);
  throw new Exception("Missing param field");
 }
 public static bool Same(PARAM.Row a,PARAM.Row b,string field){
  object x=a.Cells.First(c=>c.Def.InternalName==field).Value;
  object y=b.Cells.First(c=>c.Def.InternalName==field).Value;
  if(x is byte[] && y is byte[])return ((byte[])x).SequenceEqual((byte[])y);
  return object.Equals(x,y);
 }
 public static void Check(Dictionary<long,ESD.State> states, long first,long end, HashSet<long> waits){
  var done=new HashSet<long>();var stack=new HashSet<long>();
  foreach(long id in states.Keys.Where(k=>k>=first&&k<end))Walk(id,states,first,end,waits,done,stack);
 }
 static void Walk(long id,Dictionary<long,ESD.State> states,long first,long end,HashSet<long> waits,HashSet<long> done,HashSet<long> stack){
  if(id<first||id>=end||waits.Contains(id)||done.Contains(id))return;
  if(!stack.Add(id))throw new Exception("Busy menu cycle");
  foreach(var c in states[id].Conditions)if(c.TargetState.HasValue){
   if(!states.ContainsKey(c.TargetState.Value))throw new Exception("Missing target");
   Walk(c.TargetState.Value,states,first,end,waits,done,stack);
  }
  stack.Remove(id);done.Add(id);
 }
}
'@
function Hash($bytes){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([byte[]]$bytes))}
function Param($bundle,$name){
    $file=@($bundle.Files | Where-Object {$_.Name.EndsWith("\$name.param")})
    if($file.Count -ne 1){throw 'Missing param'}
    $def=[SoulsFormats.PARAMDEF]::XmlDeserialize((Join-Path $lib "Assets/PARAM/NR/Defs/$name.xml"),$true)
    $p=[SoulsFormats.PARAM]::Read($file[0].Bytes)
    $p.ApplyParamdef($def.GetFilteredParamdefForRegulationVersion([uint64]$bundle.Version))
    @{table=$p;file=$file[0]}
}
$regPath=Join-Path $folder 'mod/regulation.bin'
$reg=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($regPath)
if($reg.Version -ne '10350000'){throw 'Unexpected regulation version'}
# Clone only custom aliases. Original effects and native gameplay fields stay unchanged.
$effects=Param $reg 'AttachEffectParam';$pools=Param $reg 'AttachEffectTableParam'
$effectMap=@{};foreach($r in $effects.table.Rows){$effectMap[[int]$r.ID]=$r}
$poolMap=@{};foreach($r in $pools.table.Rows){if(-not $poolMap.ContainsKey([int]$r.ID)){$poolMap[[int]$r.ID]=@()};$poolMap[[int]$r.ID]+=$r}
$aliasCount=0
foreach($alias in $plan.duplicate_aliases){
    if($alias.effect_id -lt 1800000000 -or $alias.effect_id -ge 1800010000 -or $alias.pool_id -ne $alias.effect_id){throw 'Unapproved alias allocation'}
    if($effectMap.ContainsKey([int]$alias.effect_id) -or $poolMap.ContainsKey([int]$alias.pool_id)){throw 'Duplicate alias collision'}
    $src=$effectMap[[int]$alias.source_effect]
    $choices=@($poolMap[[int]$alias.source_pool] | Where-Object {([NreFull]::Get($_,'chanceWeight') -gt 0 -and [NreFull]::Get($_,'chanceWeight_dlc') -ne 0)})
    if($null -eq $src -or $choices.Count -ne 1 -or [NreFull]::Get($choices[0],'attachEffectId') -ne $alias.source_effect){throw 'Unverified deterministic alias source'}
    $copy=[SoulsFormats.PARAM+Row]::new($src);$copy.ID=[int]$alias.effect_id
    # These are project-owned group IDs, not claims about unused native IDs.
    [NreFull]::Set($copy,'compatibilityId',[int]$alias.effect_id)
    [NreFull]::Set($copy,'exclusivityId',[int]$alias.effect_id)
    foreach($cell in $src.Cells){
        if($cell.Def.InternalName -notin @('compatibilityId','exclusivityId')){
            if(-not [NreFull]::Same($copy,$src,$cell.Def.InternalName)){throw 'Alias changed gameplay or text field'}
        }
    }
    $pool=[SoulsFormats.PARAM+Row]::new($choices[0]);$pool.ID=[int]$alias.pool_id
    [NreFull]::Set($pool,'attachEffectId',[int]$alias.effect_id)
    $effects.table.Rows.Add($copy);$pools.table.Rows.Add($pool)
    $effectMap[[int]$copy.ID]=$copy;$poolMap[[int]$pool.ID]=@($pool);$aliasCount++
}
if($aliasCount -eq 0){throw 'Missing duplicate alias plan'}
$effects.file.Bytes=$effects.table.Write();$pools.file.Bytes=$pools.table.Write()
$ant=Param $reg 'EquipParamAntique'
$rowMap=@{};foreach($r in $ant.table.Rows){$rowMap[[int]$r.ID]=$r}
foreach($product in $plan.initial_products){
    if($product.id -notin $plan.relic_ids){throw 'Unexpected product ID'}
    $old=$rowMap[[int]$product.id]
    $template=$rowMap[[int]$product.template_id]
    if($null -eq $old -or $null -eq $template){throw 'Missing known row'}
    if([NreFull]::Get($template,'relicColor') -ne $product.color -or [NreFull]::Get($template,'isDeepRelic') -ne [int]($product.editor -eq 2) -or [NreFull]::Get($template,'iconId') -ne $product.icon_id){throw 'Color template mismatch'}
    $new=[SoulsFormats.PARAM+Row]::new($template);$new.ID=[int]$product.id
    foreach($field in $product.fields.PSObject.Properties){[NreFull]::Set($new,$field.Name,[int]$field.Value)}
    $index=$ant.table.Rows.IndexOf($old);$ant.table.Rows[$index]=$new
}
$ant.file.Bytes=$ant.table.Write()
$shop=Param $reg 'ShopLineupParam'
foreach($product in $plan.initial_products){
    $shopRow=@($shop.table.Rows | Where-Object ID -eq $product.shop_id)
    if($shopRow.Count -ne 1){throw 'Missing color product shop row'}
    foreach($pair in @{equipId=$product.id;value=1;costType=4;sellQuantity=-1;setNum=1;eventFlag_forStock=0;eventFlag_forRelease=0}.GetEnumerator()){
        if([NreFull]::Get($shopRow[0],$pair.Key) -ne $pair.Value){throw 'Color shop mapping, cost or stock mismatch'}
    }
}
$raw=[byte[]]$ant.file.Bytes.ToArray()
$count=[BitConverter]::ToUInt16($raw,10)
if($count -ne $ant.table.Rows.Count){throw 'Native header layout mismatch'}
$layout=@();$offsets=@(16,20,24,32,36,40)
for($i=0;$i -lt $count;$i++){
    $id=[BitConverter]::ToInt32($raw,64+24*$i)
    if($id -notin $plan.relic_ids){continue}
    $offset=[BitConverter]::ToUInt64($raw,64+24*$i+8)
    $bytes=$raw[$offset..($offset+47)]
    $row=@($ant.table.Rows | Where-Object ID -eq $id)[0]
    $fields=@('attachEffectTableId_1','attachEffectTableId_2','attachEffectTableId_3','attachEffectTableId_curse1','attachEffectTableId_curse2','attachEffectTableId_curse3')
    for($n=0;$n -lt 6;$n++){
        if([BitConverter]::ToInt32([byte[]]$bytes,$offsets[$n]) -ne [NreFull]::Get($row,$fields[$n])){throw 'Field layout mismatch'}
    }
    $layout+=@{id=$id;size=48;initial_hex=[Convert]::ToHexString([byte[]]$bytes);field_offsets=$offsets}
}
if($layout.Count -ne 8){throw 'Missing runtime row guards'}
[SoulsFormats.SFUtil]::EncryptNightreignRegulation($regPath,$reg,$reg.Compression)
$round=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($regPath)
$rAnt=Param $round 'EquipParamAntique'
foreach($name in 'AttachEffectParam','AttachEffectTableParam'){
    $rt=Param $round $name;$expected=if($name -eq 'AttachEffectParam'){$effects}else{$pools}
    if((Hash $rt.file.Bytes.ToArray()) -ne (Hash $expected.file.Bytes.ToArray())){throw 'Alias table roundtrip failed'}
}
if((Hash $rAnt.file.Bytes.ToArray()) -ne (Hash $ant.file.Bytes.ToArray())){throw 'Regulation roundtrip failed'}
$talkPath=Join-Path $folder 'mod/script/talk/m10_00_00_00.talkesdbnd.dcx'
$b=[SoulsFormats.BND4]::Read($talkPath)
$file=@($b.Files | Where-Object {$_.Name.EndsWith('\t605001000.esd')})[0]
$esd=[SoulsFormats.ESD]::Read($file.Bytes)
$original=$esd.Write();$group=$esd.StateGroups[[long]2147483643]
$originalStart=$group[[long]1]
$source=[SoulsFormats.BND4]::Read((Join-Path $root 'local/native-menu/original/script/talk/m10_00_00_00.talkesdbnd.dcx'))
$native=[SoulsFormats.ESD]::Read(($source.Files | Where-Object {$_.Name.EndsWith('\t605001000.esd')}).Bytes)
$shop=$native.StateGroups[[long]2147483643][[long]1]
$clear=$native.StateGroups[[long]2147483644][[long]8]
$show=$native.StateGroups[[long]2147483644][[long]10]
$waits=[Collections.Generic.HashSet[long]]::new()
foreach($item in $plan.states){
    if($group.ContainsKey([long]$item.id)){throw 'State collision'}
    $state=[SoulsFormats.ESD+State]::new()
    switch($item.template){
        'clear' {foreach($c in $clear.EntryCommands){$state.EntryCommands.Add([NreFull]::Copy($c))}}
        'show' {foreach($c in $show.EntryCommands){$state.EntryCommands.Add([NreFull]::Copy($c))}}
        'original_shop' {foreach($c in $shop.EntryCommands){$state.EntryCommands.Add([NreFull]::Copy($c))}}
        'dynamic_shop' {
            foreach($c in $shop.EntryCommands){$state.EntryCommands.Add([NreFull]::Copy($c))}
            $expr=[Convert]::FromHexString('8264000000820300000085A1')
            $state.EntryCommands[0].Arguments[0]=$expr
            $state.EntryCommands[0].Arguments[1]=$expr
        }
    }
    foreach($command in $item.entry){
        $args=[Collections.Generic.List[byte[]]]::new()
        foreach($a in $command.args){$args.Add([Convert]::FromHexString($a))}
        $state.EntryCommands.Add([SoulsFormats.ESD+CommandCall]::new([int]$command.bank,[int]$command.id,$args.ToArray()))
    }
    for($i=0;$i -lt @($item.conditions).Count;$i++){
        $c=$item.conditions[$i]
        if($item.template -eq 'show'){$condition=[NreFull]::Copy($show.Conditions[$i])}
        elseif($item.template -in @('original_shop','dynamic_shop')){$condition=[NreFull]::Copy($shop.Conditions[$i])}
        else{$condition=[SoulsFormats.ESD+Condition]::new([long]$c.target,[Convert]::FromHexString($c.eval))}
        $condition.TargetState=[long]$c.target;$state.Conditions.Add($condition)
    }
    $group.Add([long]$item.id,$state)
    if($item.modal){[void]$waits.Add([long]$item.id)}
}
$start=[SoulsFormats.ESD+State]::new()
$start.Conditions.Add([SoulsFormats.ESD+Condition]::new([long]$plan.root_state,[byte[]]@(0x41,0xa1)))
$group[[long]1]=$start
[NreFull]::Check($group,$plan.state_first,$plan.state_end,$waits)
foreach($item in $plan.states){foreach($c in $group[[long]$item.id].Conditions){if(-not $group.ContainsKey($c.TargetState.Value)){throw 'Dangling target'}}}
$file.Bytes=$esd.Write();$b.Write($talkPath)
$back=[SoulsFormats.BND4]::Read($talkPath)
$restored=[SoulsFormats.ESD]::Read(($back.Files | Where-Object {$_.Name.EndsWith('\t605001000.esd')}).Bytes)
foreach($item in $plan.states){[void]$restored.StateGroups[[long]2147483643].Remove([long]$item.id)}
$restored.StateGroups[[long]2147483643][[long]1]=$originalStart
if((Hash $restored.Write()) -ne (Hash $original)){throw 'Unexpected ESD change outside full editor'}
foreach($language in 'zhocn','engus'){
    $path=Join-Path $folder "mod/msg/$language/menu_dlc01.msgbnd.dcx"
    $msg=[SoulsFormats.BND4]::Read($path)
    $f=@($msg.Files | Where-Object {$_.Name.EndsWith('\EventTextForTalk.fmg')})[0]
    $text=[SoulsFormats.FMG]::Read($f.Bytes)
    $ids=[Collections.Generic.HashSet[int]]::new()
    foreach($e in $text.Entries){[void]$ids.Add($e.ID)}
    foreach($e in $plan.texts){
        if(-not $ids.Add([int]$e.id)){throw 'Text collision'}
        $text.Entries.Add([SoulsFormats.FMG+Entry]::new($text,[int]$e.id,[string]$e.$language))
    }
    $f.Bytes=$text.Write();$msg.Write($path)
    $back=[SoulsFormats.BND4]::Read($path)
    $rt=($back.Files | Where-Object {$_.Name.EndsWith('\EventTextForTalk.fmg')}).Bytes
    if((Hash $rt.ToArray()) -ne (Hash $f.Bytes.ToArray())){throw 'Text roundtrip failed'}
}
$extraction=Get-Content (Join-Path $root 'local/native-menu/extraction.json') -Raw | ConvertFrom-Json
foreach($language in 'zhocn','engus'){
    $relative="msg/$language/item_dlc01.msgbnd.dcx"
    $sourcePath=Join-Path $root "local/native-menu/original/$relative"
    $sourceHash=(Get-FileHash -LiteralPath $sourcePath).Hash
    if(@($extraction.files | Where-Object {$_.path -eq $relative -and $_.sha256 -eq $sourceHash}).Count -ne 1){throw 'Unverified item text source'}
    $msg=[SoulsFormats.BND4]::Read($sourcePath)
    $f=@($msg.Files | Where-Object {$_.Name.EndsWith('\AntiqueName.fmg')})[0]
    $text=[SoulsFormats.FMG]::Read($f.Bytes)
    $zhColors=@('红色','蓝色','黄色','绿色');$enColors=@('Red','Blue','Yellow','Green')
    foreach($product in $plan.initial_products){
        if(@($text.Entries | Where-Object ID -eq $product.id).Count){throw 'Custom item text collision'}
        if($language -eq 'zhocn'){$name='自造'+$zhColors[$product.color]+$(if($product.editor -eq 2){'深夜遗物'}else{'遗物'})}
        else{$name='Crafted '+$enColors[$product.color]+$(if($product.editor -eq 2){' Deep Relic'}else{' Relic'})}
        $text.Entries.Add([SoulsFormats.FMG+Entry]::new($text,[int]$product.id,$name))
    }
    $f.Bytes=$text.Write();$target=Join-Path $folder "mod/$relative";$msg.Write($target)
    $back=[SoulsFormats.BND4]::Read($target)
    if((Hash ($back.Files | Where-Object {$_.Name.EndsWith('\AntiqueName.fmg')}).Bytes.ToArray()) -ne (Hash $f.Bytes.ToArray())){throw 'Item name roundtrip failed'}
}
[ordered]@{schema_version=2;rows=$layout;table='EquipParamAntique';native_row_size=48;
    paramdef_sha256=(Get-FileHash -LiteralPath (Join-Path $lib 'Assets/PARAM/NR/Defs/EquipParamAntique.xml')).Hash} |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $folder 'runtime-layout.json') -Encoding utf8
[ordered]@{status='BUILD_PASS_RUNTIME_TEST_PENDING';states=@($plan.states).Count;texts=@($plan.texts).Count;
    duplicate_aliases=$aliasCount;alias_fields_verified=$true;native_row_guards=8;visible_editors=2;colors=4;shop_mapping_and_price_verified=$true;native_filter_hierarchy=$true;native_work_values=4;esd_restore_verified=$true;resource_roundtrips_verified=$true;
    original_game_modified=$false;game_verified=$false} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $folder 'full-build-report.json') -Encoding utf8
