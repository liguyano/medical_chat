[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDirectory,

    [string]$PostgresContainer = 'medical-evaluate-postgres',

    [string]$PostgresUser = 'medical',

    [string]$Database = 'medical_evaluate',

    [string]$StorageDirectory = ''
)

$ErrorActionPreference = 'Stop'

$releasePath = [System.IO.Path]::GetFullPath($ReleaseDirectory)
if (-not (Test-Path -LiteralPath $releasePath -PathType Container)) {
    throw "发布目录不存在：$releasePath"
}

$storagePath = if ($StorageDirectory) {
    [System.IO.Path]::GetFullPath($StorageDirectory)
} else {
    [System.IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot '..\backend\storage')
    )
}
if (-not (Test-Path -LiteralPath $storagePath -PathType Container)) {
    throw "应用存储目录不存在：$storagePath"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw '未找到 docker 命令，请先安装并启动 Docker Desktop。'
}
if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
    throw '未找到 tar 命令，请使用 Windows 10/11 自带 tar 或安装 bsdtar。'
}

$containerState = (& docker inspect --format '{{.State.Status}}' $PostgresContainer 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $containerState -ne 'running') {
    throw "PostgreSQL 容器未运行：$PostgresContainer"
}

$releaseName = Split-Path -Leaf $releasePath
$tagMatch = [regex]::Match($releaseName, '(?<tag>\d{8}-\d{2,})$')
$dataTag = if ($tagMatch.Success) { $tagMatch.Groups['tag'].Value } else { Get-Date -Format 'yyyyMMdd-HHmmss' }

$dumpName = "medical-evaluate-demo-postgres-$dataTag.dump"
$storageArchiveName = "medical-evaluate-demo-storage-$dataTag.tar.gz"
$dumpPath = Join-Path $releasePath $dumpName
$storageArchivePath = Join-Path $releasePath $storageArchiveName
$containerDumpPath = "/tmp/$dumpName"

Write-Warning '请确认当前 FastAPI、Next.js、Celery Worker 和 Beat 已停止写入。'
Write-Warning '本次导出将包含真实患者资料、对话、签名和音频。'

Write-Host "导出 PostgreSQL：$dumpName"
& docker exec $PostgresContainer pg_dump `
    --username=$PostgresUser `
    --dbname=$Database `
    --format=custom `
    --no-owner `
    --no-privileges `
    --file=$containerDumpPath
if ($LASTEXITCODE -ne 0) {
    throw 'PostgreSQL 数据库导出失败。'
}

$copySource = '{0}:{1}' -f $PostgresContainer, $containerDumpPath
& docker cp $copySource $dumpPath
if ($LASTEXITCODE -ne 0) {
    throw '无法从 PostgreSQL 容器复制备份文件。'
}
& docker exec $PostgresContainer rm -f $containerDumpPath

Write-Host "打包应用存储：$storageArchiveName"
& tar -czf $storageArchivePath -C $storagePath .
if ($LASTEXITCODE -ne 0) {
    throw '音频和签名存储打包失败。'
}

foreach ($path in @($dumpPath, $storageArchivePath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "未生成预期数据文件：$path"
    }
    if ((Get-Item -LiteralPath $path).Length -le 0) {
        throw "数据文件为空：$path"
    }
}

foreach ($path in @($dumpPath, $storageArchivePath)) {
    $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
    $shaLine = "$($hash.Hash.ToLowerInvariant())  $(Split-Path -Leaf $path)`n"
    $ascii = New-Object System.Text.ASCIIEncoding
    [System.IO.File]::WriteAllText("$path.sha256", $shaLine, $ascii)
}

@"
真实数据演示包：$dataTag
PostgreSQL 容器：$PostgresContainer
数据库：$Database
数据库用户：$PostgresUser
存储目录：$storagePath
PostgreSQL 备份：$dumpName
存储归档：$storageArchiveName

恢复前必须确认目标服务器为演示环境，并设置：
DEMO_RESTORE_CONFIRM=YES

恢复命令：
./deploy.sh demo-restore

Redis 不在本数据包内迁移，服务器将使用全新 Redis 数据卷。
"@ | Set-Content -LiteralPath (Join-Path $releasePath 'DEMO-DATA.txt') -Encoding UTF8

Write-Host "真实数据演示包已生成：$releasePath"
