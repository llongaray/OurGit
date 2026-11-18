# OurGit - Instalador Windows corporativo (HTTPS + SHA-256 + rollback).
# Nao altera ExecutionPolicy, App Control, WDAC, Defender ou AppLocker.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Get-OurGitBlockMessage {
    param([datetime]$Since)
    $events = @(Get-WinEvent -FilterHashtable @{
        LogName = "Microsoft-Windows-CodeIntegrity/Operational"
        StartTime = $Since.AddSeconds(-3)
        Id = 3077
    } -ErrorAction SilentlyContinue | Where-Object { $_.Message -match 'ourgit\.exe' } | Select-Object -First 3)
    if ($events.Count -eq 0) { return "Nenhum evento Code Integrity 3077 encontrado." }
    $summaries = foreach ($item in $events) {
        $match = [regex]::Match($item.Message, 'Policy ID:\{([a-fA-F0-9-]+)\}')
        if ($match.Success) { "Code Integrity 3077; Policy ID: " + $match.Groups[1].Value }
        else { "Code Integrity 3077; horario: " + $item.TimeCreated }
    }
    return ($summaries -join "; ")
}

function Invoke-OurGitVersion {
    param([string]$Executable)
    $started = Get-Date
    try {
        $output = & $Executable --version 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Retorno: $LASTEXITCODE; $($output -join ' ')" }
        $version = ($output | Out-String).Trim()
        if ($version -notmatch '^OurGit 0\.[0-9]+\.[0-9]+') {
            throw "Resposta de versao inesperada: $version"
        }
        return $version
    } catch {
        $diagnosis = Get-OurGitBlockMessage -Since $started
        throw "Windows impediu executar o OurGit. $diagnosis. Detalhe: $($_.Exception.Message). Solicite autorizacao da TI; o instalador nao altera politicas de seguranca."
    }
}

if (-not [Environment]::Is64BitOperatingSystem) { throw "OurGit requer Windows x64." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git for Windows nao encontrado no PATH." }

$base = "https://github.com/llongaray/OurGit/releases/latest/download"
$asset = "ourgit-windows-x86_64.zip"
$work = Join-Path ([IO.Path]::GetTempPath()) ("OurGit-" + [guid]::NewGuid().ToString("N"))
$dest = if ($env:OURGIT_INSTALL_DIR) { [IO.Path]::GetFullPath($env:OURGIT_INSTALL_DIR) }
        else { Join-Path $env:LOCALAPPDATA "Programs\OurGit" }
$target = Join-Path $dest "ourgit.exe"
$backup = Join-Path $work "ourgit-previous.exe"
$replaced = $false
$hadPrevious = $false
New-Item -ItemType Directory -Force -Path $work | Out-Null
try {
    $archive = Join-Path $work $asset
    $checksums = Join-Path $work "checksums.txt"
    Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset" -OutFile $archive
    Invoke-WebRequest -UseBasicParsing -Uri "$base/checksums.txt" -OutFile $checksums

    $line = Get-Content -LiteralPath $checksums |
        Where-Object { $_ -match ('^[a-fA-F0-9]{64}  ' + [regex]::Escape($asset) + '$') } |
        Select-Object -First 1
    if (-not $line) { throw "Checksum SHA-256 ausente no arquivo publicado." }
    if (-not ($line -match '^([a-fA-F0-9]{64})  ')) { throw "Checksum SHA-256 com formato invalido." }
    $expected = $Matches[1].ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -ne $actual) { throw "Checksum SHA-256 divergente. Instalacao cancelada." }

    $extracted = Join-Path $work "bin"
    Expand-Archive -LiteralPath $archive -DestinationPath $extracted -Force
    $candidate = Join-Path $extracted "ourgit.exe"
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Pacote de Release sem ourgit.exe."
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $candidate
    if ($env:OURGIT_REQUIRE_SIGNED -eq "1" -and $signature.Status -ne "Valid") {
        throw "Exigida assinatura Authenticode confiavel (OURGIT_REQUIRE_SIGNED=1); status: $($signature.Status)."
    }
    if ($signature.Status -notin @("Valid", "NotSigned")) {
        throw "Assinatura invalida ou nao confiavel: $($signature.Status)."
    }
    if ($env:OURGIT_TRUSTED_SIGNER_THUMBPRINT) {
        $required = ($env:OURGIT_TRUSTED_SIGNER_THUMBPRINT -replace '[^a-fA-F0-9]', '').ToUpperInvariant()
        $signer = if ($signature.SignerCertificate) { $signature.SignerCertificate.Thumbprint.ToUpperInvariant() } else { "" }
        if ($signature.Status -ne "Valid" -or $signer -ne $required) {
            throw "Assinatura nao corresponde ao certificado autorizado por OURGIT_TRUSTED_SIGNER_THUMBPRINT."
        }
    }
    if ($signature.Status -eq "NotSigned") {
        Write-Warning "Release nao assinada. O App Control corporativo pode bloquear o executavel."
    }

    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    $hadPrevious = Test-Path -LiteralPath $target -PathType Leaf
    if ($hadPrevious) { Copy-Item -LiteralPath $target -Destination $backup -Force }

    # Testar no caminho DEFINITIVO, pois regras WDAC podem depender desse caminho.
    $replaced = $true
    Copy-Item -LiteralPath $candidate -Destination $target -Force
    $version = Invoke-OurGitVersion -Executable $target

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $segments = @($userPath -split ';' | Where-Object { $_ })
    if ($segments -notcontains $dest) {
        [Environment]::SetEnvironmentVariable("Path", ($segments + $dest) -join ';', "User")
    }
    if (($env:Path -split ';') -notcontains $dest) { $env:Path += ";$dest" }
    Write-Host "OurGit instalado e validado: $target" -ForegroundColor Green
    Write-Host $version
    Write-Host "Assinatura Authenticode: $($signature.Status)"
}
catch {
    $reason = $_.Exception.Message
    if ($replaced) {
        try {
            if ($hadPrevious -and (Test-Path -LiteralPath $backup)) {
                Copy-Item -LiteralPath $backup -Destination $target -Force
                Write-Warning "Instalacao anterior restaurada apos bloqueio/falha da nova versao."
            } elseif (Test-Path -LiteralPath $target) {
                Remove-Item -LiteralPath $target -Force
                Write-Warning "Versao nao funcional removida (nao havia instalacao anterior)."
            }
        } catch {
            Write-Warning "Rollback falhou: $($_.Exception.Message). Confira manualmente o arquivo."
        }
    }
    throw "Falha ao instalar OurGit. $reason"
}
finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
