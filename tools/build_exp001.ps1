param(
    [string]$ProjectRoot = 'E:\Codex\Project\黑环mod',
    [switch]$InspectOnly
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path
$tools = Join-Path $project 'local\tools\Smithbox-2.2.6'
$inputFile = Join-Path $project 'local\inputs\regulation.bin'
$outputDir = Join-Path $project 'local\exp001\mod'
$outputFile = Join-Path $outputDir 'regulation.bin'
$candidateFile = Join-Path $outputDir 'regulation.unverified.bin'
$evidence = Join-Path $project 'local\evidence'
$expectedHash = '876A3CA279A4561D0C69F81FE5E510C75C59AB9A8A201694F8CF4A42C91E0268'
if ((Get-FileHash -LiteralPath $inputFile -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Unexpected input version/hash. Revalidate mappings before building.'
}
if (-not $InspectOnly -and (Test-Path -LiteralPath $outputFile)) {
    throw 'Experiment output already exists. Preserve and review it before rebuilding.'
}
foreach ($name in @('BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll')) {
    [Reflection.Assembly]::LoadFrom((Join-Path $tools $name)) | Out-Null
}
$bundle = [SoulsFormats.SFUtil]::DecryptNightreignRegulation($inputFile)
if ($bundle.Version -ne '10350000') { throw 'Unexpected regulation version' }
$entry = @($bundle.Files | Where-Object Name -Match '\\SpEffectParam.param$')
if ($entry.Count -ne 1) { throw 'Expected exactly one SpEffectParam' }
$definition = [SoulsFormats.PARAMDEF]::XmlDeserialize((Join-Path $tools 'Assets\PARAM\NR\Defs\SpEffectParam.xml'),$true)
$definition = $definition.GetFilteredParamdefForRegulationVersion([uint64]$bundle.Version)
$original = [SoulsFormats.PARAM]::Read($entry[0].Bytes)
$original.ApplyParamdef($definition)
$modified = [SoulsFormats.PARAM]::Read($entry[0].Bytes)
$modified.ApplyParamdef($definition)
$row = @($modified.Rows | Where-Object ID -eq 500830)
if ($row.Count -ne 1) { throw 'Boiled Prawn row not found uniquely' }
$cell = @($row[0].Cells | Where-Object { $_.Def.InternalName -eq 'maxHpRate' })
$duration = @($row[0].Cells | Where-Object { $_.Def.InternalName -eq 'effectEndurance' })
if ($cell.Count -ne 1 -or $cell[0].Value -ne [single]1.0 -or $duration[0].Value -ne [single]60) {
    throw 'Unexpected original effect or duration'
}
if ($InspectOnly) {
    [ordered]@{version=$bundle.Version;param='SpEffectParam';row_id=500830;field='maxHpRate';before=$cell[0].Value;duration=$duration[0].Value} | ConvertTo-Json
    exit 0
}
$cell[0].Value = [single]1.05
$entry[0].Bytes = [Memory[byte]]::new([byte[]]$modified.Write())
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
[SoulsFormats.SFUtil]::EncryptNightreignRegulation($candidateFile,$bundle,$bundle.Compression)
$roundtripBundle = [SoulsFormats.SFUtil]::DecryptNightreignRegulation($candidateFile)
$roundtripEntry = @($roundtripBundle.Files | Where-Object Name -Match '\\SpEffectParam.param$')[0]
$roundtrip = [SoulsFormats.PARAM]::Read($roundtripEntry.Bytes)
$roundtrip.ApplyParamdef($definition)
Add-Type -ReferencedAssemblies @((Join-Path $tools 'Andre.SoulsFormats.dll'), 'System.Collections', 'System.Runtime', 'System.Collections.NonGeneric') -TypeDefinition @'
using System;
using System.Collections;
using SoulsFormats;
public static class NreSingleCellCheck {
    public static int Verify(PARAM a, PARAM b) {
        if (a.Rows.Count != b.Rows.Count) throw new Exception("Row count changed");
        int changes = 0;
        for (int i=0; i<a.Rows.Count; ++i) {
            var x=a.Rows[i]; var y=b.Rows[i];
            if(x.ID!=y.ID || x.Name!=y.Name || x.Cells.Count!=y.Cells.Count)
                throw new Exception("Row identity/shape changed");
            for(int j=0; j<x.Cells.Count; ++j) {
                var c=x.Cells[j]; var d=y.Cells[j];
                if(c.Def.InternalName!=d.Def.InternalName) throw new Exception("Field shape changed");
                if (!StructuralComparisons.StructuralEqualityComparer.Equals(c.Value,d.Value)) {
                    if(x.ID!=500830 || c.Def.InternalName!="maxHpRate" ||
                       Convert.ToSingle(c.Value)!=1.0f || Convert.ToSingle(d.Value)!=1.05f)
                        throw new Exception("Unexpected field change");
                    changes++;
                }
            }
        }
        if(changes!=1) throw new Exception("Expected exactly one changed cell");
        return changes;
    }
}
'@
$count = [NreSingleCellCheck]::Verify($original,$roundtrip)
$originalBundle = [SoulsFormats.SFUtil]::DecryptNightreignRegulation($inputFile)
if ($originalBundle.Files.Count -ne $roundtripBundle.Files.Count) { throw 'Bundle file count changed' }
for ($i=0; $i -lt $originalBundle.Files.Count; $i++) {
    $a=$originalBundle.Files[$i]; $b=$roundtripBundle.Files[$i]
    if ($a.Name -ne $b.Name -or $a.ID -ne $b.ID) { throw 'Bundle file identity changed' }
    if ($a.Name -notmatch '\\SpEffectParam.param$') {
        $ha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($a.Bytes.ToArray()))
        $hb=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($b.Bytes.ToArray()))
        if ($ha -ne $hb) { throw "Unexpected changed file: $($a.Name)" }
    }
}
Move-Item -LiteralPath $candidateFile -Destination $outputFile
$report=[ordered]@{
    experiment='EXP-001'; carrier='Boiled Prawn'; goods_id=830
    regulation_internal_version=$bundle.Version
    original_sha256=$expectedHash
    modified_sha256=(Get-FileHash -LiteralPath $outputFile -Algorithm SHA256).Hash
    param='SpEffectParam'; row_id=500830; field='maxHpRate'
    before=1.0; after=1.05; unchanged_duration_seconds=60
    changed_cells=$count; other_bundle_files_unchanged=$true
    roundtrip_validation='PASS'; game_test='PENDING'
    library_sha256=(Get-FileHash -LiteralPath (Join-Path $tools 'Andre.SoulsFormats.dll') -Algorithm SHA256).Hash
}
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'EXP-001-build.json') -Encoding utf8
$report | ConvertTo-Json
