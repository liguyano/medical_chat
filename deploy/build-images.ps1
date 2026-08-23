[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PublicOrigin,

    [string]$ReleaseTag = (Get-Date -Format 'yyyyMMdd-HHmmss'),

    [ValidateSet('linux/amd64', 'linux/arm64')]
    [string]$Platform = 'linux/amd64',

    [string]$OutputDirectory = ''
)

$ErrorActionPreference = 'Stop'

$deployDirectory = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $deployDirectory '..')).Path
$releaseDirectory = if ($OutputDirectory) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    Join-Path $repoRoot "release\$ReleaseTag"
}

$backendImage = "medical-evaluate-backend:$ReleaseTag"
$frontendImage = "medical-evaluate-frontend:$ReleaseTag"
$archivePath = Join-Path $releaseDirectory "medical-evaluate-images-$ReleaseTag.tar"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw '未找到 docker 命令，请先安装并启动 Docker Desktop。'
}

if ([string]::IsNullOrWhiteSpace($PublicOrigin)) {
    throw 'PublicOrigin 必须是完整 HTTPS 来源，例如 https://app.example.com。'
}
if ($PublicOrigin -notmatch '^https://[^/]+$') {
    throw 'PublicOrigin 必须是完整 HTTPS 来源，例如 https://app.example.com。'
}

New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null

Write-Host "构建后端镜像：$backendImage"
& docker buildx build `
    --platform $Platform `
    --file (Join-Path $deployDirectory 'backend.Dockerfile') `
    --tag $backendImage `
    --load `
    $repoRoot
if ($LASTEXITCODE -ne 0) {
    throw '后端镜像构建失败。'
}

Write-Host "构建前端镜像：$frontendImage"
& docker buildx build `
    --platform $Platform `
    --file (Join-Path $deployDirectory 'frontend.Dockerfile') `
    --build-arg NEXT_PUBLIC_DATA_MODE=api `
    --build-arg "NEXT_PUBLIC_API_BASE_URL=$PublicOrigin" `
    --build-arg NEXT_PUBLIC_DIALOG_TRANSPORT=websocket `
    --build-arg NEXT_PUBLIC_API_TIMEOUT_MS=15000 `
    --tag $frontendImage `
    --load `
    $repoRoot
if ($LASTEXITCODE -ne 0) {
    throw '前端镜像构建失败。'
}

$backendPlatform = (& docker image inspect $backendImage --format '{{.Os}}/{{.Architecture}}').Trim()
$frontendPlatform = (& docker image inspect $frontendImage --format '{{.Os}}/{{.Architecture}}').Trim()
if ($backendPlatform -ne $Platform -or $frontendPlatform -ne $Platform) {
    Write-Warning "镜像平台检查结果：backend=$backendPlatform frontend=$frontendPlatform，目标=$Platform。"
}

Write-Host "导出镜像包：$archivePath"
& docker save --output $archivePath $backendImage $frontendImage
if ($LASTEXITCODE -ne 0) {
    throw '镜像导出失败。'
}

$hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
"$($hash.Hash.ToLowerInvariant())  $(Split-Path -Leaf $archivePath)" |
    Set-Content -LiteralPath "$archivePath.sha256" -Encoding ASCII

$runtimeFiles = @(
    'docker-compose.yaml',
    'deploy.sh',
    'restore-demo-data.sh',
    'baota-reverse-proxy.conf',
    '.env.production.example',
    'config.production.example.yaml'
)
foreach ($file in $runtimeFiles) {
    Copy-Item -LiteralPath (Join-Path $deployDirectory $file) `
        -Destination (Join-Path $releaseDirectory $file) -Force
}

$releaseDeployScript = Join-Path $releaseDirectory 'deploy.sh'
$releaseDeployScriptText = [System.IO.File]::ReadAllText($releaseDeployScript)
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $releaseDeployScript,
    $releaseDeployScriptText.Replace("`r`n", "`n"),
    $utf8WithoutBom
)

@"
镜像发布包：$ReleaseTag
目标平台：$Platform
公网来源：$PublicOrigin
后端镜像：$backendImage
前端镜像：$frontendImage
镜像文件：$(Split-Path -Leaf $archivePath)
SHA256：$($hash.Hash.ToLowerInvariant())

服务器部署前请：
1. 将 IMAGE_TAG=$ReleaseTag 写入服务器的 .env.production；
2. 执行 docker load -i $(Split-Path -Leaf $archivePath)；
3. 执行 ./deploy.sh config && ./deploy.sh up。
"@ | Set-Content -LiteralPath (Join-Path $releaseDirectory 'RELEASE.txt') -Encoding UTF8

Write-Host "发布包已生成：$releaseDirectory"
