<#
.SYNOPSIS
    推送到 GitHub — 一键测API

.DESCRIPTION
    初始化远端、设置提交身份、推送 main 分支、可选打 tag 并发 Release。
    所有身份通过参数传入，脚本内不留占位符。

.EXAMPLE
    .\push.ps1 -User 383827453-max -Name "Liu" -Email "me@example.com"

.EXAMPLE
    # 连 tag 和 Release 一起发（需已安装 gh 并登录）
    .\push.ps1 -User 383827453-max -Name "Liu" -Email "me@example.com" -Tag v1.2.2 -Release
#>
param(
    [Parameter(Mandatory = $true)][string]$User,
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Email,
    [string]$Repo = "OneClickModelTest",
    [string]$Branch = "main",
    [string]$Tag,
    [switch]$Release,
    [switch]$Public
)

$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"

Write-Host "==> 仓库: $User/$Repo  分支: $Branch" -ForegroundColor Cyan

# 1) 本仓库提交身份
git config user.name  $Name
git config user.email $Email
Write-Host "    身份: $Name <$Email>"

# 2) 远端
$existing = git remote 2>$null
if ($existing -contains "origin") { git remote remove origin }
git remote add origin "https://github.com/$User/$Repo.git"
Write-Host "    远端: https://github.com/$User/$Repo.git"

# 3) 推送
git push -u origin $Branch
if ($LASTEXITCODE -ne 0) { throw "push 失败 (exit=$LASTEXITCODE)" }
Write-Host "==> 已推送 $Branch" -ForegroundColor Green

# 4) 可选 tag
if ($Tag) {
    git tag -d $Tag 2>$null | Out-Null
    git tag -a $Tag -m "$Repo $Tag"
    git push origin $Tag
    Write-Host "==> 已推送 tag $Tag" -ForegroundColor Green
}

# 5) 可选 Release（需 gh 已登录）
if ($Release) {
    if (-not (Test-Path $gh)) { throw "未找到 gh: $gh" }
    if (-not $Tag) { throw "-Release 需要同时指定 -Tag" }

    Write-Host "==> 本地打包中 ..." -ForegroundColor Cyan
    pyinstaller build.spec --noconfirm
    $exe = Get-ChildItem "dist\*.exe" | Select-Object -First 1
    if (-not $exe) { throw "打包产物未找到，检查 build.spec" }
    Write-Host "    产物: $($exe.FullName) ($([math]::Round($exe.Length/1MB,1)) MB)"

    & $gh release create $Tag "$($exe.FullName)" `
        --repo "$User/$Repo" `
        --title "$Repo $Tag" `
        --notes "见 CHANGELOG 或提交记录。"
    Write-Host "==> Release 已发布" -ForegroundColor Green
}

Write-Host ""
Write-Host "完成: https://github.com/$User/$Repo" -ForegroundColor Green
