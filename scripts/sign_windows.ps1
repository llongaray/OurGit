# OurGit: assinatura Authenticode opcional no runner Windows.
# Secrets: OURGIT_CODESIGN_PFX_BASE64 e OURGIT_CODESIGN_PFX_PASSWORD.
# Sem secrets: build NAO ASSINADA e claramente identificada como tal.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$exe = Join-Path (Get-Location) "dist\ourgit.exe"
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Executavel ausente: dist/ourgit.exe" }
$releaseDir = Join-Path (Get-Location) "release"
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
$pfxB64 = $env:OURGIT_CODESIGN_PFX_BASE64
$pfxPass = $env:OURGIT_CODESIGN_PFX_PASSWORD
$hasPfx = -not [string]::IsNullOrWhiteSpace($pfxB64)
$hasPassword = -not [string]::IsNullOrWhiteSpace($pfxPass)
if ($hasPfx -xor $hasPassword) { throw "Configure ambos segredos de assinatura ou nenhum." }
if (-not $hasPfx -and $env:OURGIT_REQUIRE_SIGNED_RELEASE -eq "1") {
    throw "Assinatura exigida, mas certificado ainda nao configurado."
}
$signingMode = "unsigned"
$publisher = $null
$thumbprint = $null
$pfxFile = Join-Path $env:RUNNER_TEMP ("ourgit-sign-" + [guid]::NewGuid().ToString("N") + ".pfx")
$imported = $null
try {
    if ($hasPfx) {
        [IO.File]::WriteAllBytes($pfxFile, [Convert]::FromBase64String($pfxB64))
        $securePassword = ConvertTo-SecureString -String $pfxPass -AsPlainText -Force
        $imported = Import-PfxCertificate -FilePath $pfxFile -Password $securePassword -CertStoreLocation 'Cert:\CurrentUser\My'
        if (-not $imported -or -not $imported.HasPrivateKey) { throw "PFX sem chave privada autorizada." }
        if ($imported.NotAfter.ToUniversalTime() -le (Get-Date).ToUniversalTime()) { throw "Certificado expirado." }
        $thumbprint = $imported.Thumbprint
        $publisher = $imported.Subject
        $sdkDir = Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Windows Kits\10\bin"
        $tools = @(Get-ChildItem -LiteralPath $sdkDir -Filter "signtool.exe" -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } | Sort-Object FullName -Descending)
        if ($tools.Count -lt 1) { throw "SignTool do Windows SDK nao localizado no runner." }
        $signtool = $tools[0].FullName
        & $signtool sign /sha1 $thumbprint /s My /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 $exe
        if ($LASTEXITCODE -ne 0) { throw "SignTool sign falhou com codigo $LASTEXITCODE." }
        & $signtool verify /pa /v $exe
        if ($LASTEXITCODE -ne 0) { throw "SignTool verify /pa falhou com codigo $LASTEXITCODE." }
        $sig = Get-AuthenticodeSignature -LiteralPath $exe
        if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Thumbprint -ne $thumbprint) {
            throw "Assinatura nao validada pelo runner."
        }
        $signingMode = "authenticode"
        Write-Host "Windows executavel assinado: $publisher"
    } else {
        Write-Warning "Sem certificado: executavel Windows permanece NAO ASSINADO. App Control empresarial pode impedir execucao."
    }
}
finally {
    if ($imported) {
        $certFile = 'Cert:\CurrentUser\My\' + $imported.Thumbprint
        Remove-Item -LiteralPath $certFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $pfxFile) {
        Remove-Item -LiteralPath $pfxFile -Force -ErrorAction SilentlyContinue
    }
}
$report = [ordered]@{
    app = "OurGit"
    platform = "windows-x86_64"
    signing_mode = $signingMode
    authenticode_status = (Get-AuthenticodeSignature -LiteralPath $exe).Status.ToString()
    publisher = $publisher
    certificate_thumbprint = $thumbprint
    exe_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
}
$report | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $releaseDir "windows-signature.json") -Encoding UTF8
Write-Host "Metadados de assinatura gerados em release/windows-signature.json"
