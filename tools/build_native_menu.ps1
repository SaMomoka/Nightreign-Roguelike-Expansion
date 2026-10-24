param(
    [Parameter(Mandatory=$true)][string]$Spec,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$ProjectRoot='E:\Codex\Project\黑环mod'
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$output=[IO.Path]::GetFullPath($OutputDirectory)
$local=[IO.Path]::GetFullPath((Join-Path $root 'local'))+[IO.Path]::DirectorySeparatorChar
if(-not $output.StartsWith($local,[StringComparison]::OrdinalIgnoreCase)){throw 'Output outside project/local'}
if(Test-Path -LiteralPath $output){throw 'Output already exists'}
$plan=Get-Content -LiteralPath $Spec -Raw | ConvertFrom-Json
if($plan.schema_version -ne 1 -or @($plan.presets).Count -lt 1 -or @($plan.presets).Count -gt 6){throw 'Invalid menu specification'}
$ids=@{}
foreach($preset in $plan.presets){
    if($preset.shop_row_id -lt 10000 -or $preset.shop_row_id -gt 10999 -or $ids.ContainsKey([int]$preset.shop_row_id)){throw 'Invalid or repeated shop row'}
    $ids[[int]$preset.shop_row_id]=$true
    foreach($lang in 'zhocn','engus'){
        if([string]::IsNullOrWhiteSpace($preset.labels.$lang) -or $preset.labels.$lang.Length -gt 80){throw 'Invalid menu label'}
    }
}
$lib=Join-Path $root 'local/tools/Smithbox-2.2.6'
[Environment]::CurrentDirectory=$lib
Set-Location -LiteralPath $lib
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
$original=Join-Path $root 'local/native-menu/original'
$pins=@{
    'script/talk/m10_00_00_00.talkesdbnd.dcx'='43D5005F1934A37121CA2589C58684E73964F2440B1D13BB79443AC689796CD1'
    'msg/zhocn/menu_dlc01.msgbnd.dcx'='A56F88BEBA7D8ABA36D2D436E9EF2E08E28A2189EEE87075F792B39B774A9E52'
    'msg/engus/menu_dlc01.msgbnd.dcx'='E33F1C338878DA423D95CF54589072D99425F2A92C10603E5C93BDA9323184DB'
}
foreach($path in $pins.Keys){
    if((Get-FileHash -LiteralPath (Join-Path $original $path)).Hash -ne $pins[$path]){throw 'Original menu version changed'}
}
function Bytes($hex){return ,([Convert]::FromHexString($hex))}
function Number([int]$number){return ,([byte[]](@(0x82)+[BitConverter]::GetBytes($number)+@(0xA1)))}
function Command($source){
    $copy=[SoulsFormats.ESD+CommandCall]::new()
    $copy.CommandBank=$source.CommandBank;$copy.CommandID=$source.CommandID
    foreach($arg in $source.Arguments){$copy.Arguments.Add([byte[]]$arg.Clone())}
    return $copy
}
function Condition($source){
    $copy=[SoulsFormats.ESD+Condition]::new()
    $copy.TargetState=$source.TargetState;$copy.Evaluator=[byte[]]$source.Evaluator.Clone()
    foreach($call in $source.PassCommands){$copy.PassCommands.Add((Command $call))}
    foreach($sub in $source.Subconditions){$copy.Subconditions.Add((Condition $sub))}
    return $copy
}
function State($source){
    $copy=[SoulsFormats.ESD+State]::new()
    foreach($field in 'EntryCommands','ExitCommands','WhileCommands'){
        foreach($call in $source.$field){$copy.$field.Add((Command $call))}
    }
    foreach($cond in $source.Conditions){$copy.Conditions.Add((Condition $cond))}
    return $copy
}
function Go([long]$target){return [SoulsFormats.ESD+Condition]::new($target,(Bytes '41A1'))}
function Digest($bytes){return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([byte[]]$bytes))}
function Verify-Binder($expected,$readback){
    if($expected.Files.Count -ne $readback.Files.Count -or $expected.Version -ne $readback.Version){throw 'Binder structure changed'}
    for($i=0;$i -lt $expected.Files.Count;$i++){
        $a=$expected.Files[$i];$b=$readback.Files[$i]
        if($a.ID -ne $b.ID -or $a.Name -ne $b.Name -or $a.Flags -ne $b.Flags -or
           (Digest $a.Bytes.ToArray()) -ne (Digest $b.Bytes.ToArray())){throw 'Binder roundtrip mismatch'}
    }
}
$talkPath='script/talk/m10_00_00_00.talkesdbnd.dcx'
$bundle=[SoulsFormats.BND4]::Read((Join-Path $original $talkPath))
$entry=@($bundle.Files | Where-Object Name -match '\\t605001000\.esd$')
if($entry.Count -ne 1){throw 'Merchant not unique'}
$esd=[SoulsFormats.ESD]::Read($entry[0].Bytes)
$menu=$esd.StateGroups[[long]2147483644]
$shop=$esd.StateGroups[[long]2147483643]
$originalEsd=[SoulsFormats.ESD]::Read($entry[0].Bytes)
if($shop[[long]1].EntryCommands.Count -ne 1 -or
   $shop[[long]1].EntryCommands[0].CommandBank -ne 1 -or $shop[[long]1].EntryCommands[0].CommandID -ne 155 -or
   [Convert]::ToHexString($shop[[long]1].EntryCommands[0].Arguments[0]) -ne '8210270000A1' -or
   [Convert]::ToHexString($menu[[long]11].Conditions[0].Evaluator) -ne '5784A74195A1'){throw 'Native command guard changed'}
$listTemplate=$menu[[long]9].EntryCommands[0]
if($listTemplate.CommandBank -ne 1 -or $listTemplate.CommandID -ne 149 -or $listTemplate.Arguments.Count -ne 5){throw 'List template changed'}
function List-Entry([int]$choice,[int]$text){
    $call=Command $listTemplate
    $call.Arguments[0]=Number $choice;$call.Arguments[1]=Number $text;$call.Arguments[3]=Number $choice
    return $call
}
# Project-local state and FMG IDs; these are new allocations, not claimed native IDs.
$newStates=8+@($plan.presets).Count
for($i=0;$i -lt $newStates;$i++){
    if($shop.ContainsKey([long](100000+$i))){throw 'NRE state collision'}
}
$originalShop=State $shop[[long]1]
$shop[[long]100003]=$originalShop
$clear=State $menu[[long]8]
$clear.Conditions.Clear();$clear.Conditions.Add((Go 100000));$shop[[long]1]=$clear
$rootList=[SoulsFormats.ESD+State]::new()
$rootList.EntryCommands.Add((List-Entry 1 1900102000))
$rootList.EntryCommands.Add((List-Entry 2 1900102001))
$rootList.EntryCommands.Add((List-Entry 99 1900102002))
$rootList.Conditions.Add((Go 100001));$shop[[long]100000]=$rootList
function Display([long]$target,[long]$cancel){
    $state=State $menu[[long]10]
    $state.Conditions[0].TargetState=$target;$state.Conditions[1].TargetState=$cancel
    return $state
}
function Choice([int]$choice,[long]$target){
    $condition=Condition $menu[[long]11].Conditions[0]
    # Preserve the native query + cache expression; replace only its integer comparison operand.
    $literal=Number $choice
    $condition.Evaluator=[byte[]](@(0x57,0x84,0xA7)+$literal[0..4]+@(0x95,0xA1))
    $condition.TargetState=$target
    return $condition
}
$shop[[long]100001]=Display 100002 10
$dispatch=[SoulsFormats.ESD+State]::new()
$dispatch.Conditions.Add((Choice 1 100003));$dispatch.Conditions.Add((Choice 2 100004))
$dispatch.Conditions.Add((Go 10));$shop[[long]100002]=$dispatch
$subClear=State $menu[[long]8]
$subClear.Conditions.Clear();$subClear.Conditions.Add((Go 100005));$shop[[long]100004]=$subClear
$subList=[SoulsFormats.ESD+State]::new()
$subDispatch=[SoulsFormats.ESD+State]::new()
for($i=0;$i -lt @($plan.presets).Count;$i++){
    $subList.EntryCommands.Add((List-Entry ($i+1) (1900102010+$i)))
    $subDispatch.Conditions.Add((Choice ($i+1) (100008+$i)))
    $selected=State $originalShop
    $selected.EntryCommands[0].Arguments[0]=Number $plan.presets[$i].shop_row_id
    $selected.EntryCommands[0].Arguments[1]=Number $plan.presets[$i].shop_row_id
    $selected.Conditions[0].TargetState=100004
    $shop[[long](100008+$i)]=$selected
}
$subList.EntryCommands.Add((List-Entry 99 1900102003))
$subList.Conditions.Add((Go 100006));$shop[[long]100005]=$subList
$subDispatch.Conditions.Add((Go 1));$shop[[long]100007]=$subDispatch
$shop[[long]100006]=Display 100007 1
# Removing just the intended insertion must restore the original ESD semantic serialization.
$probe=[SoulsFormats.ESD]::Read($esd.Write())
$probeShop=$probe.StateGroups[[long]2147483643]
for($i=0;$i -lt $newStates;$i++){$probeShop.Remove([long](100000+$i)) | Out-Null}
$probeShop[[long]1]=$originalEsd.StateGroups[[long]2147483643][[long]1]
if((Digest $probe.Write()) -ne (Digest $originalEsd.Write())){throw 'Unexpected original ESD changes'}
foreach($group in $esd.StateGroups.Values){
    function Check-Targets($conditions,$states){
        foreach($condition in $conditions){
            if($null -ne $condition.TargetState -and -not $states.ContainsKey([long]$condition.TargetState)){throw 'Dangling state target'}
            Check-Targets $condition.Subconditions $states
        }
    }
    foreach($state in $group.Values){Check-Targets $state.Conditions $group}
}
$entry[0].Bytes=[Memory[byte]]::new([byte[]]$esd.Write())
$graph=@()
foreach($key in (@([long]1)+@(100000..(100000+$newStates-1)))){
    $state=$shop[[long]$key]
    $graph += [ordered]@{state=$key;
        commands=@($state.EntryCommands | ForEach-Object {
            [ordered]@{bank=$_.CommandBank;id=$_.CommandID;args=@($_.Arguments | ForEach-Object {[Convert]::ToHexString($_)})}
        });
        conditions=@($state.Conditions | ForEach-Object {
            [ordered]@{target=$_.TargetState;evaluator=[Convert]::ToHexString($_.Evaluator)}
        })}
}
$talkOutput=Join-Path $output $talkPath
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($talkOutput)) | Out-Null
$bundle.Write($talkOutput)
Verify-Binder $bundle ([SoulsFormats.BND4]::Read($talkOutput))
$textCounts=@{}
foreach($lang in 'zhocn','engus'){
    $path="msg/$lang/menu_dlc01.msgbnd.dcx"
    $textBundle=[SoulsFormats.BND4]::Read((Join-Path $original $path))
    $textEntry=@($textBundle.Files | Where-Object Name -match '\\EventTextForTalk\.fmg$')
    if($textEntry.Count -ne 1){throw 'Menu text resource not unique'}
    $fmg=[SoulsFormats.FMG]::Read($textEntry[0].Bytes)
    $textMap=@{
        1900102000=@{zhocn='原商店';engus='Original shop'}
        1900102001=@{zhocn='NRE 遗物选择';engus='NRE relic selection'}
        1900102002=@{zhocn='离开';engus='Leave'}
        1900102003=@{zhocn='返回';engus='Back'}
    }
    for($i=0;$i -lt @($plan.presets).Count;$i++){$textMap[1900102010+$i]=$plan.presets[$i].labels}
    foreach($id in ($textMap.Keys | Sort-Object)){
        if(@($fmg.Entries | Where-Object ID -eq $id).Count){throw 'NRE text ID collision'}
        $fmg.Entries.Add([SoulsFormats.FMG+Entry]::new($fmg,[int]$id,[string]$textMap[$id].$lang))
    }
    $textEntry[0].Bytes=[Memory[byte]]::new([byte[]]$fmg.Write())
    $destination=Join-Path $output $path
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
    $textBundle.Write($destination)
    Verify-Binder $textBundle ([SoulsFormats.BND4]::Read($destination))
    $textCounts[$lang]=$textMap.Count
}
[ordered]@{status='NATIVE_MENU_BUILT_GAME_PENDING';native_talk_id=605001000;
    modified_original_states=1;new_states=$newStates;added_texts=$textCounts;
    original_esd_restoration_verified=$true;binder_roundtrip_verified=$true;
    all_state_targets_resolved=$true;intentional_cycles='Menu back navigation; modal waits retained from native states';
    source_hashes=$pins;presets=$plan.presets;graph=$graph;game_verified=$false} |
    ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $output 'native-menu-report.json') -Encoding utf8
Write-Output "Built native merchant menu: presets=$(@($plan.presets).Count)"
