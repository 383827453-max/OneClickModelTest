# 推送到 GitHub — 一键测API
# 用法: 先把 GITHUB_USER 和 REPO 改成你的，然后在本目录运行  .\push.ps1

$GITHUB_USER = "YOUR_GITHUB_USERNAME"
$REPO        = "OneClickModelTest"

# 1) 确认 git 身份（只对本仓库生效）
git config user.name  "YOUR_NAME"
git config user.email "YOUR_EMAIL"

# 2) 绑定远端
git remote remove origin 2>$null
git remote add origin "https://github.com/$GITHUB_USER/$REPO.git"

# 3) 推送
git push -u origin main

Write-Host ""
Write-Host "如果要发布 exe 到 Release：" -ForegroundColor Cyan
Write-Host "  1. 本地打包:  pyinstaller build.spec --noconfirm"
Write-Host "  2. gh release create v1.2.1 `"dist/一键测模型.exe`" -t `"v1.2.1`""
Write-Host "  （gh 未安装则去 https://github.com/$GITHUB_USER/$REPO/releases/new 手动拖入）"
