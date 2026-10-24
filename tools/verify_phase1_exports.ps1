param([string]$ProjectRoot = 'E:\Codex\Project\黑环mod')
$ErrorActionPreference = 'Stop'
$lib = Join-Path $ProjectRoot 'local\tools\Smithbox-2.2.6'
$inputFile = Join-Path $ProjectRoot 'local\inputs\regulation.bin'
$expected = '876A3CA279A4561D0C69F81FE5E510C75C59AB9A8A201694F8CF4A42C91E0268'
if ((Get-FileHash -LiteralPath $inputFile).Hash -ne $expected) { throw 'Input hash mismatch' }
foreach ($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll') {
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
$bundle = [SoulsFormats.SFUtil]::DecryptNightreignRegulation($inputFile)
$checks = [ordered]@{
    ItemTableParam = @('itemCategory','itemId','chanceWeight','quantity','onlyForClass','eventFlagId','disableParam_NT','unknown_6','unknown_7')
    EquipParamGoods = @('goodsType','vagrantItemLotId')
    PermanentBuffParam = @('spEffectId','numericValue','displayNumericValue','displayPercentageSymbol','graceSpEffectId')
    SpEffectParam = @('maxHpRate','maxMpRate','maxStaminaRate','physicsAttackRate','slashDamageCutRate','blowDamageCutRate','thrustDamageCutRate','neutralDamageCutRate','magicDamageCutRate','fireDamageCutRate','thunderDamageCutRate','darkDamageCutRate','effectEndurance','spCategory','saveCategory')
    ItemLotParam_enemy = @('lotItemId01','lotItemId02','lotItemId03','lotItemId04','lotItemId05','lotItemId06','lotItemId07','lotItemId08','lotItemCategory01','lotItemCategory02','lotItemCategory03','lotItemCategory04','lotItemCategory05','lotItemCategory06','lotItemCategory07','lotItemCategory08','lotItemBasePoint01','lotItemBasePoint02','lotItemBasePoint03','lotItemBasePoint04','lotItemBasePoint05','lotItemBasePoint06','lotItemBasePoint07','lotItemBasePoint08')
    NpcParam = @('rewardItemLot_1','rewardItemLot_2')
}
$results = @()
foreach ($name in $checks.Keys) {
    $entry = @($bundle.Files | Where-Object { $_.Name.EndsWith("\$name.param") })
    if ($entry.Count -ne 1) { throw "Missing table: $name" }
    $param = [SoulsFormats.PARAM]::Read($entry[0].Bytes)
    $defName = if($name -eq 'ItemLotParam_enemy'){'ItemLotParam'}else{$name}
    $def = [SoulsFormats.PARAMDEF]::XmlDeserialize((Join-Path $lib "Assets\PARAM\NR\Defs\$defName.xml"),$true)
    $param.ApplyParamdef($def.GetFilteredParamdefForRegulationVersion([uint64]$bundle.Version))
    $csvPath = Join-Path $ProjectRoot "local\evidence\$name.csv"
    $csv = @(Import-Csv -LiteralPath $csvPath)
    if ($csv.Count -ne $param.Rows.Count) { throw "Row count mismatch: $name" }
    $fieldIndexes = @{}
    for ($j=0; $j -lt $param.Rows[0].Cells.Count; $j++) {
        $fieldIndexes[$param.Rows[0].Cells[$j].Def.InternalName] = $j
    }
    foreach ($field in $checks[$name]) {
        if (-not $fieldIndexes.ContainsKey($field)) { throw "Unknown field: $name.$field" }
    }
    for ($i=0; $i -lt $csv.Count; $i++) {
        $row = $param.Rows[$i]
        # Row ordinal preserves repeated pool IDs without losing candidates.
        if ([int]$csv[$i].ID -ne $row.ID) { throw "ID/order mismatch: $name ordinal $i" }
        foreach ($field in $checks[$name]) {
            $actual = $row.Cells[$fieldIndexes[$field]].Value
            if ([Convert]::ChangeType($csv[$i].$field,$actual.GetType(),[Globalization.CultureInfo]::InvariantCulture) -ne $actual) {
                throw "Value mismatch: $name ordinal $i field $field"
            }
        }
    }
    $results += [ordered]@{ table=$name;rows=$csv.Count;fields=$checks[$name];status='PASS';csv_sha256=(Get-FileHash -LiteralPath $csvPath).Hash }
}
$report = [ordered]@{regulation_sha256=$expected;status='PASS';scope='IDs, ordinal and listed numeric fields; imported display names are not authenticated';tables=$results}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ProjectRoot 'local\evidence\phase1-export-verification.json') -Encoding utf8
$results | ForEach-Object { "$($_.table): $($_.rows) rows PASS" }
