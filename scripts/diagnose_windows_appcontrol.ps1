# Diagnostico OurGit no Windows: SOMENTE LEITURA, sem alterar App Control.
# Opcional: -CompareReleases compara arquivos ZIP oficiais sem executar EXEs.
param([switch]$CompareReleases)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$exe = Join-Path $env:LOCALAPPDATA "Programs\OurGit\ourgit.exe"
Write-Host ""
Write-Host "=== ARQUIVO INSTALADO ===" -ForegroundColor Cyan
if (Test-Path -LiteralPath $exe -PathType Leaf) {
    $f = Get-Item -LiteralPath $exe
    $sig = Get-AuthenticodeSignature -LiteralPath $exe
    [pscustomobject]@{
        File = $f.FullName
        Bytes = $f.Length
        SHA256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
        Authenticode = $sig.Status.ToString()
        Signer = if ($sig.SignerCertificate) { $sig.SignerCertificate.Subject } else { "(nenhum)" }
    } | Format-List
} else {
    Write-Warning "Arquivo OurGit instalado nao encontrado."
}
function Get-OurGitEventData {
    param($Record)
    $xml = [xml]$Record.ToXml()
    $values = [ordered]@{}
    foreach ($data in @($xml.Event.EventData.Data)) {
        if ($null -eq $data) { continue }
        $key = [string]$data.Name
        if ([string]::IsNullOrWhiteSpace($key)) { $key = "Value$($values.Count + 1)" }
        $values[$key] = [string]$data.InnerText
    }
    return $values
}

Write-Host ""
Write-Host "=== CODE INTEGRITY 3077 / 3089 / 3092 ===" -ForegroundColor Cyan
$events = @(Get-WinEvent -FilterHashtable @{
    LogName = "Microsoft-Windows-CodeIntegrity/Operational"
    StartTime = (Get-Date).AddDays(-2)
    Id = 3077, 3089, 3092
} -ErrorAction SilentlyContinue)
$blocks = @($events | Where-Object { $_.Id -eq 3077 -and $_.Message -match "ourgit\.exe" })
if ($blocks.Count -eq 0) {
    Write-Host "Sem evento 3077 de OurGit nas ultimas 48h; ausencia de evento nao prova autorizacao."
}
foreach ($block in ($blocks | Select-Object -First 5)) {
    $xml = [xml]$block.ToXml()
    $activity = [string]$xml.Event.System.Correlation.ActivityID
    $match = [regex]::Match($block.Message, "Policy ID:\{([a-fA-F0-9-]+)\}")
    [pscustomobject]@{
        Time = $block.TimeCreated
        Event = $block.Id
        Policy = if ($match.Success) { $match.Groups[1].Value } else { "indisponivel" }
        ActivityId = $activity
    } | Format-List
    $blockData = Get-OurGitEventData -Record $block
    if ($blockData.Count -gt 0) {
        Write-Host "Campos estruturados do bloqueio 3077:" -ForegroundColor DarkCyan
        $blockData.GetEnumerator() | ForEach-Object {
            [pscustomobject]@{ Campo = $_.Key; Valor = $_.Value }
        } | Format-Table -AutoSize -Wrap
    }
    if ($activity) {
        foreach ($other in $events) {
            if ($other.Id -notin @(3089, 3092)) { continue }
            $otherXml = [xml]$other.ToXml()
            if ([string]$otherXml.Event.System.Correlation.ActivityID -eq $activity) {
                Write-Host ("Evento correlacionado " + $other.Id + " (dados estruturados):")
                $data = Get-OurGitEventData -Record $other
                if ($data.Count -gt 0) {
                    $data.GetEnumerator() | ForEach-Object {
                        [pscustomobject]@{ Campo = $_.Key; Valor = $_.Value }
                    } | Format-Table -AutoSize -Wrap
                } else {
                    Write-Host "EventData indisponivel neste registro."
                }
            }
        }
    }
}
Write-Host ""
Write-Host "=== CARREGAMENTO DE POLITICAS (3099) ===" -ForegroundColor Cyan
$policyEvents = @(Get-WinEvent -FilterHashtable @{
    LogName = "Microsoft-Windows-CodeIntegrity/Operational"
    StartTime = (Get-Date).AddDays(-14)
    Id = 3099
} -ErrorAction SilentlyContinue | Select-Object -First 30)
$policyId = "0283ac0f-fff1-49ae-ada1-8a933130cad6"
$matched = 0
foreach ($entry in $policyEvents) {
    $details = Get-OurGitEventData -Record $entry
    $flat = ($details.Values -join ' ') + ' ' + $entry.Message
    if ($flat -match [regex]::Escape($policyId)) {
        $matched++
        Write-Host ("Politica encontrada: " + $entry.TimeCreated)
        $details.GetEnumerator() | ForEach-Object {
            [pscustomobject]@{ Campo = $_.Key; Valor = $_.Value }
        } | Format-Table -AutoSize -Wrap
    }
}
if ($matched -eq 0) {
    Write-Host "Sem evento 3099 correspondente nos ultimos 14 dias (o log pode ter sido rotacionado)."
}
Write-Host "Este relatorio e somente leitura; a TI deve confirmar a regra de autorizacao."

if ($CompareReleases) {
    Write-Host ""
    Write-Host "=== COMPARANDO RELEASES OFFLINE, SEM EXECUTAR O CODIGO ===" -ForegroundColor Cyan
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("OurGit-Compare-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        foreach ($version in @("v0.2.0", "v0.3.1")) {
            $asset = "ourgit-windows-x86_64.zip"
            $base = "https://github.com/llongaray/OurGit/releases/download/$version"
            $dir = Join-Path $tmp $version
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            $zip = Join-Path $dir $asset
            $check = Join-Path $dir "checksums.txt"
            Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset" -OutFile $zip
            Invoke-WebRequest -UseBasicParsing -Uri "$base/checksums.txt" -OutFile $check
            $line = Get-Content -LiteralPath $check |
                Where-Object { $_ -match ('^[a-fA-F0-9]{64}  ' + [regex]::Escape($asset) + '$') } |
                Select-Object -First 1
            if (-not $line) { throw "Checksum ausente: $version" }
            if (-not ($line -match '^([a-fA-F0-9]{64})  ')) { throw "Checksum malformado: $version" }
            $expected = $Matches[1].ToUpperInvariant()
            $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToUpperInvariant()
            if ($actual -ne $expected) { throw "ZIP com checksum divergente: $version" }
            $unpack = Join-Path $dir "bin"
            Expand-Archive -LiteralPath $zip -DestinationPath $unpack -Force
            $binary = Join-Path $unpack "ourgit.exe"
            if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) { throw "Sem EXE: $version" }
            $auth = Get-AuthenticodeSignature -LiteralPath $binary
            [pscustomobject]@{
                Release = $version
                SHA256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash
                Bytes = (Get-Item -LiteralPath $binary).Length
                Authenticode = $auth.Status.ToString()
                Signer = if ($auth.SignerCertificate) { $auth.SignerCertificate.Subject } else { "(nenhum)" }
            } | Format-List
        }
    }
    finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "Diagnostico concluido: nenhum EXE baixado foi executado." -ForegroundColor Green
