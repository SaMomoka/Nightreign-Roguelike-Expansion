param([Parameter(Mandatory=$true)][string]$Package,[string]$ProjectRoot='E:\Codex\Project\黑环mod')
$ErrorActionPreference='Stop'
$root=(Resolve-Path $ProjectRoot).Path;$folder=(Resolve-Path $Package).Path
if(-not $folder.StartsWith((Join-Path $root 'local/packages')+[IO.Path]::DirectorySeparatorChar)){throw 'Outside packages'}
$plan=Get-Content (Join-Path $folder 'training-plan.json') -Raw | ConvertFrom-Json
if($plan.request_flag -ne 10009880 -or $plan.entries.Count -lt 12){throw 'Invalid training plan'}
$lib=Join-Path $root 'local/tools/Smithbox-2.2.6';[Environment]::CurrentDirectory=$lib;Set-Location $lib
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){[Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null}
Add-Type -ReferencedAssemblies @((Join-Path $lib 'Andre.SoulsFormats.dll'),'System.Collections','System.Runtime','System.Linq') -TypeDefinition @'
using System;using System.Linq;using System.Collections.Generic;using SoulsFormats;
public static class TrainingBuild {
 public static ESD.CommandCall Copy(ESD.CommandCall c){return new ESD.CommandCall(c.CommandBank,c.CommandID,c.Arguments.Select(a=>(byte[])a.Clone()).ToArray());}
 public static ESD.Condition Copy(ESD.Condition c){var n=new ESD.Condition();n.TargetState=c.TargetState;n.Evaluator=(byte[])c.Evaluator.Clone();foreach(var p in c.PassCommands)n.PassCommands.Add(Copy(p));foreach(var p in c.Subconditions)n.Subconditions.Add(Copy(p));return n;}
 public static void Set(PARAM.Row r,string key,double value){var c=r.Cells.Single(x=>x.Def.InternalName==key);c.Value=Convert.ChangeType(value,c.Value.GetType());}
 public static int Get(PARAM.Row r,string key){return Convert.ToInt32(r.Cells.Single(x=>x.Def.InternalName==key).Value);}
 public static void Sort(PARAM p){var sorted=p.Rows.OrderBy(r=>r.ID).ToList();p.Rows.Clear();p.Rows.AddRange(sorted);}
}
'@
function Hash($b){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([byte[]]$b))}
function Param($b,$name){
 $f=@($b.Files | Where-Object {$_.Name.EndsWith("\$name.param")});if($f.Count -ne 1){throw 'Missing param'}
 $dn=if($name -in @('ItemLotParam_enemy','ItemLotParam_map')){'ItemLotParam'}else{$name}
 $d=[SoulsFormats.PARAMDEF]::XmlDeserialize((Join-Path $lib "Assets/PARAM/NR/Defs/$dn.xml"),$true)
 $p=[SoulsFormats.PARAM]::Read($f[0].Bytes);$p.ApplyParamdef($d.GetFilteredParamdefForRegulationVersion([uint64]$b.Version))
 return @{file=$f[0];table=$p;original=$p.Write();added=[Collections.Generic.List[int]]::new()}
}
function One($p,$id){$r=@($p.table.Rows | Where-Object ID -eq $id);if($r.Count -ne 1){throw "Ambiguous source $id"};return $r[0]}
function Clone($p,$src,$id){if(@($p.table.Rows | Where-Object ID -eq $id).Count){throw 'Custom param collision'};$r=[SoulsFormats.PARAM+Row]::new($src);$r.ID=[int]$id;$p.table.Rows.Add($r);$p.added.Add([int]$id);return $r}
function SetCell($r,$field,$value){[TrainingBuild]::Set($r,$field,$value)}
$regPath=Join-Path $folder 'mod/regulation.bin';$reg=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($regPath)
if($reg.Version -ne '10350000'){throw 'Unsupported regulation'}
$params=@{};foreach($n in 'EquipParamGoods','PermanentBuffParam','SpEffectParam','ItemTableParam','ItemLotParam_enemy','ItemLotParam_map','NpcParam'){$params[$n]=Param $reg $n}
foreach($e in $plan.entries){if($e.goods_id -le 0 -or $e.goods_id -gt 0x00ffffff){throw 'Goods ID exceeds packed item payload'}}
foreach($e in @($plan.entries | Where-Object custom)){
 $g=Clone $params.EquipParamGoods (One $params.EquipParamGoods $e.source_goods) $e.goods_id
 if([TrainingBuild]::Get($g,'goodsType') -ne 11 -or [TrainingBuild]::Get($g,'vagrantItemLotId') -ne $e.source_permanent){throw 'Unverified permanent buff path'}
 $p=Clone $params.PermanentBuffParam (One $params.PermanentBuffParam $e.source_permanent) $e.goods_id
 if([TrainingBuild]::Get($p,'spEffectId') -ne $e.source_effect){throw 'Unverified SpEffect path'}
 $s=Clone $params.SpEffectParam (One $params.SpEffectParam $e.source_effect) $e.goods_id
 SetCell $s 'spEffectTextId_1' $e.goods_id
 SetCell $g 'vagrantItemLotId' $e.goods_id;SetCell $p 'spEffectId' $e.goods_id;SetCell $p 'numericValue' $e.numeric_value
 foreach($field in $e.fields.PSObject.Properties){SetCell $s $field.Name $field.Value}
}
foreach($e in @($plan.entries | Where-Object {-not $_.token})){
 $g=One $params.EquipParamGoods $e.goods_id
 if([TrainingBuild]::Get($g,'goodsType') -ne 11){throw 'Candidate is not a permanent buff'}
 $pb=One $params.PermanentBuffParam ([TrainingBuild]::Get($g,'vagrantItemLotId'))
 $fx=One $params.SpEffectParam ([TrainingBuild]::Get($pb,'spEffectId'))
 if($e.custom -and ([TrainingBuild]::Get($fx,'spEffectTextId_1') -ne $e.goods_id)){throw 'Custom text reference mismatch'}
 if(-not $e.custom -and ([TrainingBuild]::Get($fx,'spEffectTextId_1') -ne $e.text_id -or [TrainingBuild]::Get($pb,'spEffectId') -ne $e.source_effect)){throw 'Native candidate differs from export'}
}
if($plan.token_goods){
 $token=Clone $params.EquipParamGoods (One $params.EquipParamGoods 8000) $plan.token_goods
 if([TrainingBuild]::Get($token,'goodsType') -ne 2){throw 'Unverified key item template'}
 foreach($field in 'isDrop','enable_ActiveBigRune','isConsume','isEquip','isDeposit','disableParam_NT','useLimitSpEffectType','enableVisualCodex'){SetCell $token $field 0}
 SetCell $token 'vagrantItemLotId' -1;SetCell $token 'maxNum' 1;SetCell $token 'iconId' 20291
 if([TrainingBuild]::Get($token,'goodsType') -ne 2 -or [TrainingBuild]::Get($token,'refId_default') -ne -1){throw 'Token must not be an equipable consumable'}
 foreach($e in @($plan.entries | Where-Object custom)){
  $lot=Clone $params.ItemLotParam_map (One $params.ItemLotParam_map 1) $e.redeem_lot
  for($slot=1;$slot -le 8;$slot++){
   $suffix=$slot.ToString('00');SetCell $lot "lotItemId$suffix" 0;SetCell $lot "lotItemCategory$suffix" 0;SetCell $lot "lotItemBasePoint$suffix" 0;SetCell $lot "lotItemNum$suffix" 0
  }
  SetCell $lot 'lotItemId01' $e.goods_id;SetCell $lot 'lotItemCategory01' 1;SetCell $lot 'lotItemBasePoint01' 1000;SetCell $lot 'lotItemNum01' 1;SetCell $lot 'getItemFlagId' 0
 }
}
$srcPool=@($params.ItemTableParam.table.Rows | Where-Object {$_.ID -eq 4200100 -and [TrainingBuild]::Get($_,'itemId') -eq 8000000})
if($srcPool.Count -ne 1 -or [TrainingBuild]::Get($srcPool[0],'itemCategory') -ne 1){throw 'Unverified goods pool'}
for($i=0;$i -lt 3;$i++){
 $r=Clone $params.ItemTableParam $srcPool[0] $plan.pool_ids[$i]
 SetCell $r 'itemId' $plan.entries[$i].goods_id;SetCell $r 'chanceWeight' 100;SetCell $r 'eventFlagId' 0;SetCell $r 'onlyForClass' 0
 $lot=Clone $params.ItemLotParam_enemy (One $params.ItemLotParam_enemy 6000052) (1900620000+$i)
 if([TrainingBuild]::Get($lot,'lotItemCategory01') -ne 7 -or [TrainingBuild]::Get($lot,'lotItemBasePoint01') -ne 1000){throw 'Unverified native reward path'}
 SetCell $lot 'lotItemId01' $plan.pool_ids[$i]
}
$npc=Clone $params.NpcParam (One $params.NpcParam 500010300) 1900600000
SetCell $npc 'rewardItemLot_1' 1900620000;SetCell $npc 'rewardItemLot_2' 1900620000;SetCell $npc 'itemLotId_enemy' -1;SetCell $npc 'itemLotId_map' -1;SetCell $npc 'dropType' 1
foreach($n in $params.Keys){
 $p=$params[$n];$added=@($p.table.Rows | Where-Object {$_.ID -in $p.added})
 foreach($r in $added){[void]$p.table.Rows.Remove($r)}
 if((Hash $p.table.Write()) -ne (Hash $p.original)){throw "Original param changed: $n"}
 foreach($r in $added){$p.table.Rows.Add($r)}
 [TrainingBuild]::Sort($p.table);$p.file.Bytes=$p.table.Write()
}
$raw=[byte[]]$params.ItemTableParam.file.Bytes.ToArray();$count=[BitConverter]::ToUInt16($raw,10);$layout=@()
for($i=0;$i -lt $count;$i++){
 $id=[BitConverter]::ToInt32($raw,64+24*$i);if($id -notin $plan.pool_ids){continue}
 $off=[BitConverter]::ToUInt64($raw,64+24*$i+8);$bytes=[byte[]]$raw[$off..($off+35)]
 if([BitConverter]::ToInt32($bytes,8) -ne [TrainingBuild]::Get((One $params.ItemTableParam $id),'itemId')){throw 'Pool layout mismatch'}
 $layout+=@{id=$id;initial_hex=[Convert]::ToHexString($bytes);item_offset=8;size=36}
}
if($layout.Count -ne 3){throw 'Missing owned pools'}
$layout | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $folder 'training-layout.json') -Encoding utf8
[SoulsFormats.SFUtil]::EncryptNightreignRegulation($regPath,$reg,$reg.Compression)
$round=[SoulsFormats.SFUtil]::DecryptNightreignRegulation($regPath)
foreach($n in $params.Keys){
 $check=Param $round $n
 foreach($r in @($check.table.Rows | Where-Object {$_.ID -in $params[$n].added})){[void]$check.table.Rows.Remove($r)}
 if((Hash $check.table.Write()) -ne (Hash $params[$n].original)){throw "Final original param changed: $n"}
}
foreach($f in $reg.Files){$r=@($round.Files | Where-Object Name -eq $f.Name);if($r.Count -ne 1 -or (Hash $r[0].Bytes.ToArray()) -ne (Hash $f.Bytes.ToArray())){throw 'Regulation roundtrip mismatch'}}

# Add one invisible, non-combat reward carrier near the existing training interaction.
$extract=Get-Content (Join-Path $root 'local/training/extraction.json') -Raw | ConvertFrom-Json
foreach($f in $extract.files){if((Get-FileHash (Join-Path $root "local/training/original/$($f.path)")).Hash -ne $f.sha256){throw 'Training source changed'}}
$mapRelative='map/mapstudio/m10_00_00_00.msb.dcx';$mapSource=Join-Path $root "local/training/original/$mapRelative"
$map=[SoulsFormats.MSB_NR]::Read($mapSource);$mapOriginal=$map.Write()
$carrier=@($map.Parts.Enemies | Where-Object {$_.Name -eq 'c0100_9014' -and $_.TalkID -eq 609001000 -and $_.EntityData.EntityID -eq 10000640})
if($carrier.Count -ne 1 -or @($map.Parts.GetEntries() | Where-Object {$_.EntityData.EntityID -eq 10000980}).Count){throw 'Map source/collision mismatch'}
$clone=$carrier[0].DeepCopy();$clone.Name='c0100_9980';$clone.InstanceID=9980;$clone.EntityData.EntityID=10000980
$clone.EntityData.EntityGroupIDs=[uint32[]]@(0,0,0,0,0,0,0,0);$clone.TalkID=0;$clone.NpcParamId=1900600000
if(($plan.spawn_reference_entities -join ',') -ne '10000404,10000405'){throw 'Unapproved training ground anchors'}
$anchors=@($map.Parts.Enemies | Where-Object {$_.EntityData.EntityID -in $plan.spawn_reference_entities})
if($anchors.Count -ne 2 -or @($anchors | Where-Object {$_.ModelName -ne 'c8131'}).Count -ne 0 -or [Math]::Abs($anchors[0].Position.Y-$anchors[1].Position.Y) -gt 0.5){throw 'Training anchor geometry changed'}
$spawnX=($anchors[0].Position.X+$anchors[1].Position.X)/2
$spawnZ=($anchors[0].Position.Z+$anchors[1].Position.Z)/2
$spawnY=[Math]::Max($anchors[0].Position.Y,$anchors[1].Position.Y)+0.25
$clone.Position=[Numerics.Vector3]::new($spawnX,$spawnY,$spawnZ);$map.Parts.Enemies.Add($clone)
$dest=Join-Path $folder "mod/$mapRelative";[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($dest)) | Out-Null;$map.Write($dest)
$rmap=[SoulsFormats.MSB_NR]::Read($dest);$rm=@($rmap.Parts.Enemies | Where-Object Name -eq 'c0100_9980');if($rm.Count -ne 1){throw 'Missing carrier'}
if([Numerics.Vector3]::Distance($rm[0].Position,$clone.Position) -gt 0.001){throw 'Spawn position roundtrip failed'};[void]$rmap.Parts.Enemies.Remove($rm[0]);if((Hash $rmap.Write()) -ne (Hash $mapOriginal)){throw 'Other map entities changed'}

$eventRelative='event/m10_00_00_00.emevd.dcx';$ev=[SoulsFormats.EMEVD]::Read((Join-Path $root "local/training/original/$eventRelative"));$eventOriginal=$ev.Write()
if(@($ev.Events | Where-Object ID -eq 10009880).Count){throw 'Event collision'}
$event=[SoulsFormats.EMEVD+Event]::new([long]10009880,[SoulsFormats.EMEVD+Event+RestBehaviorType]::Restart)
foreach($i in $plan.event_instructions){$event.Instructions.Add([SoulsFormats.EMEVD+Instruction]::new([int]$i.bank,[int]$i.id,[Convert]::FromHexString($i.hex)))}
$ev.Events.Add($event);$init=@($ev.Events | Where-Object ID -eq 0)[0];$before=$init.Instructions.Count
$init.Instructions.Add([SoulsFormats.EMEVD+Instruction]::new(2000,0,[Convert]::FromHexString($plan.event_init)))
foreach($ne in $plan.numeric_events){
 if(@($ev.Events | Where-Object ID -eq $ne.id).Count){throw 'Numeric event collision'}
 $extra=[SoulsFormats.EMEVD+Event]::new([long]$ne.id,[SoulsFormats.EMEVD+Event+RestBehaviorType]::Restart)
 foreach($ni in $ne.instructions){$extra.Instructions.Add([SoulsFormats.EMEVD+Instruction]::new([int]$ni.bank,[int]$ni.id,[Convert]::FromHexString($ni.hex)))}
 $ev.Events.Add($extra);$init.Instructions.Add([SoulsFormats.EMEVD+Instruction]::new(2000,0,[byte[]]([BitConverter]::GetBytes([int]0)+[BitConverter]::GetBytes([int]$ne.id)+[BitConverter]::GetBytes([int]0))))
}
$dest=Join-Path $folder "mod/$eventRelative";[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($dest)) | Out-Null;$ev.Write($dest)
$re=[SoulsFormats.EMEVD]::Read($dest);[void]$re.Events.Remove(@($re.Events | Where-Object ID -eq 10009880)[0]);(@($re.Events | Where-Object ID -eq 0)[0]).Instructions.RemoveAt($before)
foreach($ne in $plan.numeric_events){[void]$re.Events.Remove(@($re.Events | Where-Object ID -eq $ne.id)[0]);(@($re.Events | Where-Object ID -eq 0)[0]).Instructions.RemoveAt($before)}
if((Hash $re.Write()) -ne (Hash $eventOriginal)){throw 'Other events changed'}

$talk=Join-Path $folder 'mod/script/talk/m10_00_00_00.talkesdbnd.dcx';$b=[SoulsFormats.BND4]::Read($talk)
foreach($targetScript in 't607001000.esd','t609001000.esd'){
$f=@($b.Files | Where-Object {$_.Name.EndsWith(('\'+$targetScript))})[0];$esd=[SoulsFormats.ESD]::Read($f.Bytes);$old=$esd.Write()
$group=$esd.StateGroups[[long]2147483644];$original=$group[[long]1]
$merchant=[SoulsFormats.ESD]::Read((([SoulsFormats.BND4]::Read((Join-Path $root 'local/native-menu/original/script/talk/m10_00_00_00.talkesdbnd.dcx'))).Files | Where-Object {$_.Name.EndsWith('\t605001000.esd')}).Bytes)
$clear=$merchant.StateGroups[[long]2147483644][[long]8];$show=$merchant.StateGroups[[long]2147483644][[long]10]
foreach($item in $plan.states){
 if($group.ContainsKey([long]$item.id)){throw 'Training state collision'};$s=[SoulsFormats.ESD+State]::new()
 $template=switch($item.template){'clear' {$clear};'show' {$show};'original' {$original};default {$null}}
 if($null -ne $template){foreach($c in $template.EntryCommands){$s.EntryCommands.Add([TrainingBuild]::Copy($c))}}
 foreach($c in $item.entry){$args=[Collections.Generic.List[byte[]]]::new();foreach($a in $c.args){$args.Add([Convert]::FromHexString($a))};$s.EntryCommands.Add([SoulsFormats.ESD+CommandCall]::new([int]$c.bank,[int]$c.id,$args.ToArray()))}
 for($i=0;$i -lt $item.conditions.Count;$i++){
  $c=$item.conditions[$i];$cond=if($item.template -in @('show','original')){[TrainingBuild]::Copy($template.Conditions[$i])}else{[SoulsFormats.ESD+Condition]::new([long]$c.target,[Convert]::FromHexString($c.eval))}
  $cond.TargetState=[long]$c.target;$s.Conditions.Add($cond)
 }
 $group.Add([long]$item.id,$s)
}
$s=[SoulsFormats.ESD+State]::new();$s.Conditions.Add([SoulsFormats.ESD+Condition]::new([long]$plan.root_state,[byte[]]@(65,161)));$group[[long]1]=$s
if($plan.token_goods -and $targetScript -eq 't607001000.esd'){
 $idle=$esd.StateGroups[[long]2147483647][[long]1]
 $idle.Conditions.Insert(0,[SoulsFormats.ESD+Condition]::new([long]6,[Convert]::FromHexString($plan.auto_open_eval)))
 $esd.StateGroups[[long]2147483647][[long]2].Conditions.Insert(0,[SoulsFormats.ESD+Condition]::new([long]6,[Convert]::FromHexString($plan.auto_open_eval)))
}
$f.Bytes=$esd.Write();$b.Write($talk);$rb=[SoulsFormats.BND4]::Read($talk);$rs=[SoulsFormats.ESD]::Read(($rb.Files | Where-Object {$_.Name.EndsWith(('\'+$targetScript))}).Bytes)
foreach($item in $plan.states){[void]$rs.StateGroups[[long]2147483644].Remove([long]$item.id)};$rs.StateGroups[[long]2147483644][[long]1]=$original
if($plan.token_goods -and $targetScript -eq 't607001000.esd'){$rs.StateGroups[[long]2147483647][[long]1].Conditions.RemoveAt(0);$rs.StateGroups[[long]2147483647][[long]2].Conditions.RemoveAt(0)}
if((Hash $rs.Write()) -ne (Hash $old)){throw 'Original training script changed outside menu'}
}
foreach($lang in 'zhocn','engus'){
 $path=Join-Path $folder "mod/msg/$lang/menu_dlc01.msgbnd.dcx";$msg=[SoulsFormats.BND4]::Read($path)
 $f=@($msg.Files | Where-Object {$_.Name.EndsWith('\EventTextForTalk.fmg')})[0];$fm=[SoulsFormats.FMG]::Read($f.Bytes)
 foreach($t in $plan.texts){if(@($fm.Entries | Where-Object ID -eq $t.id).Count){throw 'Training text collision'};$fm.Entries.Add([SoulsFormats.FMG+Entry]::new($fm,[int]$t.id,[string]$t.text))};$f.Bytes=$fm.Write();$msg.Write($path)
 $path=Join-Path $folder "mod/msg/$lang/item_dlc01.msgbnd.dcx";$msg=[SoulsFormats.BND4]::Read($path)
 foreach($suffix in 'GoodsName.fmg','GoodsInfo.fmg','GoodsCaption.fmg','PermanentBuffName.fmg','PermanentBuffInfo.fmg','AttachEffectName.fmg','AttachEffectInfo.fmg'){
  $f=@($msg.Files | Where-Object {$_.Name.EndsWith('\'+$suffix)});if($f.Count -ne 1){throw "Missing $suffix"};$fm=[SoulsFormats.FMG]::Read($f[0].Bytes)
  foreach($e in $plan.entries){if($e.goods_id -le 0 -or $e.goods_id -gt 0x00ffffff){throw 'Goods ID exceeds packed item payload'}}
foreach($e in @($plan.entries | Where-Object custom)){if(@($fm.Entries | Where-Object ID -eq $e.goods_id).Count){throw 'Buff text collision'};$fm.Entries.Add([SoulsFormats.FMG+Entry]::new($fm,[int]$e.goods_id,[string]$e.name))};$f[0].Bytes=$fm.Write()
 }
 if($plan.token_goods){
  foreach($bank in 'GoodsName.fmg','GoodsInfo.fmg','GoodsCaption.fmg'){
   $tf=@($msg.Files | Where-Object {$_.Name.EndsWith('\'+$bank)})[0];$tm=[SoulsFormats.FMG]::Read($tf.Bytes)
   if(@($tm.Entries | Where-Object ID -eq $plan.token_goods).Count){throw 'Token text collision'}
   $label=if($bank -eq 'GoodsName.fmg'){'数值强化'}else{'领取后，从数值强化中任选一项。取消可稍后继续选择。'}
   $tm.Entries.Add([SoulsFormats.FMG+Entry]::new($tm,[int]$plan.token_goods,$label));$tf.Bytes=$tm.Write()
  }
 }
 $msg.Write($path)
 $verifyMsg=[SoulsFormats.BND4]::Read($path)
 foreach($bank in 'PermanentBuffName.fmg','PermanentBuffInfo.fmg','AttachEffectName.fmg','AttachEffectInfo.fmg'){
  $vfm=[SoulsFormats.FMG]::Read(($verifyMsg.Files | Where-Object {$_.Name.EndsWith('\'+$bank)}).Bytes)
  foreach($e in @($plan.entries | Where-Object custom)){
   $vt=@($vfm.Entries | Where-Object ID -eq $e.goods_id)
   if($vt.Count -ne 1 -or $vt[0].Text -ne $e.name){throw 'Custom buff text roundtrip mismatch'}
  }
 }
}
@{status='BUILD_PASS_GAME_TEST_PENDING';spawn_position=@($spawnX,$spawnY,$spawnZ);spawn_reference_entities=@(10000404,10000405);custom_buffs=@($plan.entries | Where-Object custom).Count;native_controls=@($plan.entries | Where-Object {-not $_.custom -and -not $_.token}).Count;numeric_choice_experimental=[bool]$plan.token_goods;owned_pool_rows=3;original_params_preserved=$true;original_map_preserved=$true;original_events_preserved=$true;original_training_preserved=$true;game_verified=$false;drop_command='2004[37] Force Character Treasure: training reward path requires game test'} | ConvertTo-Json | Set-Content (Join-Path $folder 'training-build-report.json') -Encoding utf8
