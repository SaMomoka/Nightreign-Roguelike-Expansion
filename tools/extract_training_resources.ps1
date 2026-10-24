param([string]$ProjectRoot='E:\Codex\Project\黑环mod')
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $ProjectRoot).Path
$runtime=Get-Content -LiteralPath (Join-Path $root 'local/runtime.json') -Raw | ConvertFrom-Json
$game=$runtime.game
$lib=Join-Path $root 'local/tools/Smithbox-2.2.6'
$keySource=Join-Path $root 'local/tools/uxm-source/UXM-Selective-Unpack-master/UXM/ArchiveKeys.cs'
$keysText=(Get-Content -LiteralPath $keySource -Raw).Split('EldenRingNightreignKeys')[1]
$keys=@{}
foreach($match in [regex]::Matches($keysText,'\["(Data[0-3])"\]\s*=\s*@"(-----BEGIN RSA PUBLIC KEY-----[\s\S]*?-----END RSA PUBLIC KEY-----)"')){
    $keys[$match.Groups[1].Value]=$match.Groups[2].Value
}
if($keys.Count -ne 4){throw 'Missing documented Nightreign archive keys'}
foreach($dll in 'BouncyCastle.Cryptography.dll','ZstdNet.dll','Andre.SoulsFormats.dll'){
    [Reflection.Assembly]::LoadFrom((Join-Path $lib $dll)) | Out-Null
}
Add-Type -CompilerOptions '/nowarn:1701,1702' -ReferencedAssemblies @((Join-Path $lib 'BouncyCastle.Cryptography.dll'),'System.Runtime','System.Collections') -TypeDefinition @'
using System;
using System.IO;
using Org.BouncyCastle.OpenSsl;
using Org.BouncyCastle.Crypto;
using Org.BouncyCastle.Crypto.Engines;
public static class NreArchiveReader {
 public static ulong Hash(string path) {
  ulong value=0;
  foreach(char c in ("/"+path.TrimStart('/').Replace('\\','/')).ToLowerInvariant())
   value=unchecked(value*133+c);
  return value;
 }
 public static byte[] Header(string path,string pem) {
  byte[] bytes=File.ReadAllBytes(path);
  if(bytes.Length>=4 && bytes[0]==66 && bytes[1]==72 && bytes[2]==68 && bytes[3]==53)return bytes;
  var engine=new RsaEngine();
  using(var reader=new StringReader(pem))
   engine.Init(false,(AsymmetricKeyParameter)new PemReader(reader).ReadObject());
  int width=engine.GetInputBlockSize(), outputWidth=engine.GetOutputBlockSize();
  if(bytes.Length%width!=0)throw new Exception("Partial RSA block");
  using(var output=new MemoryStream()) {
   for(int offset=0;offset<bytes.Length;offset+=width) {
    byte[] decoded=engine.ProcessBlock(bytes,offset,width);
    if(decoded.Length>outputWidth)throw new Exception("Invalid RSA output");
    output.Write(new byte[outputWidth-decoded.Length]);
    output.Write(decoded);
   }
   return output.ToArray();
  }
 }
}
'@
$wanted=@('event/m10_00_00_00.emevd.dcx','event/common_func.emevd.dcx','map/mapstudio/m10_00_00_00.msb.dcx')
$hashes=@{}
foreach($path in $wanted){$hashes[[NreArchiveReader]::Hash($path)]=$path}
$output=Join-Path $root 'local/training/original'
$found=@{};$records=@()
foreach($archive in 'Data0','Data1','Data2','Data3'){
    if($found.Count -eq $wanted.Count){break}
    $header=Join-Path $game "$archive.bhd"
    Write-Output "Inspecting $archive"
    $decoded=[NreArchiveReader]::Header($header,$keys[$archive])
    $bhd=[SoulsFormats.BHD5]::Read([Memory[byte]]::new($decoded),[SoulsFormats.BHD5+Game]::EldenRing)
    $stream=[IO.File]::OpenRead((Join-Path $game "$archive.bdt"))
    try{
        foreach($bucket in $bhd.Buckets){
            foreach($file in $bucket){
                if(-not $hashes.ContainsKey($file.FileNameHash)){continue}
                $path=$hashes[$file.FileNameHash]
                if($found.ContainsKey($path)){throw "Ambiguous original resource: $path"}
                $bytes=$file.ReadFile($stream)
                $destination=Join-Path $output $path
                [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
                if(Test-Path -LiteralPath $destination){
                    $digest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))
                    if((Get-FileHash -LiteralPath $destination).Hash -ne $digest){throw 'Existing original differs; refusing overwrite'}
                }else{[IO.File]::WriteAllBytes($destination,$bytes)}
                $found[$path]=$true
                $records += [ordered]@{path=$path;archive=$archive;size=$bytes.Length;
                    sha256=(Get-FileHash -LiteralPath $destination).Hash;
                    archive_header_sha256=(Get-FileHash -LiteralPath $header).Hash}
            }
        }
    }finally{$stream.Dispose()}
}
if($found.Count -ne $wanted.Count){throw 'Some native menu resources not found; preserve partial evidence'}
[ordered]@{status='EXTRACTED_ORIGINAL';files=$records;
    key_source_sha256=(Get-FileHash -LiteralPath $keySource).Hash;
    installed_regulation_sha256=(Get-FileHash -LiteralPath (Join-Path $game 'regulation.bin')).Hash} |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $root 'local/training/extraction.json') -Encoding utf8
