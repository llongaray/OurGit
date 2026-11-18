# OurGit: instalador Windows PowerShell x64, com validacao SHA-256.
$ErrorActionPreference = "Stop"
$base = "https://github.com/llongaray/OurGit/releases/latest/download"
$asset = "ourgit-windows-x86_64.zip"
if (-not [Environment]::Is64BitOperatingSystem) { throw "OurGit exige Windows x64." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git for Windows nao encontrado." }
$work = Join-Path ([IO.Path]::GetTempPath()) ("OurGit-" + [guid]::NewGuid().ToString("N"))
$dest = if ($env:OURGIT_INSTALL_DIR) { $env:OURGIT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\OurGit" }
New-Item -ItemType Directory -Force -Path $work | Out-Null
try {
    $archive = Join-Path $work $asset
    $checksums = Join-Path $work "checksums.txt"
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset" -OutFile $archive
    Invoke-WebRequest -UseBasicParsing -Uri "$base/checksums.txt" -OutFile $checksums
    $pattern = '^([a-fA-F0-9]{64})  ' + [regex]::Escape($asset) + '$'
    $line = Get-Content $checksums | Where-Object { $_ -match $pattern } | Select-Object -First 1
    if (-not $line -or $line -notmatch $pattern) { throw "Checksum nao encontrado para Windows." }
    $expected = $Matches[1].ToLowerInvariant()
    $actual = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -ne $actual) { throw "SHA-256 nao confere." }
    $extracted = Join-Path $work "bin"
    Expand-Archive -LiteralPath $archive -DestinationPath $extracted -Force
    $exe = Join-Path $extracted "ourgit.exe"
    if (-not (Test-Path $exe)) { throw "Executavel nao encontrado no ZIP." }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item -LiteralPath $exe -Destination (Join-Path $dest "ourgit.exe") -Force
    $upath = [Environment]::GetEnvironmentVariable("Path","User")
    $parts = @($upath -split ";" | Where-Object { $_ })
    if ($parts -notcontains $dest) { [Environment]::SetEnvironmentVariable("Path",($parts + $dest) -join ";","User") }
    if (($env:Path -split ";") -notcontains $dest) { $env:Path += ";$dest" }
    Write-Host "OurGit instalado em: $dest\ourgit.exe"
    & (Join-Path $dest "ourgit.exe") --version
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
