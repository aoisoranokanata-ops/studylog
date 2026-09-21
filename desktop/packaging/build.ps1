# StudyLog 母艦のビルド（PyInstaller onedir）
# 使い方:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $PSScriptRoot
Set-Location $projectDir

$distDir = Join-Path $projectDir "dist"
$buildDir = Join-Path $projectDir "build"
$specFile = Join-Path $projectDir "packaging\studylog.spec"

Write-Host "テストを実行します..." -ForegroundColor Cyan
$env:PYTHONPATH = Join-Path $projectDir "src"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "テストが失敗したのでビルドを中止します" }
Remove-Item Env:\QT_QPA_PLATFORM

Write-Host "ビルドします..." -ForegroundColor Cyan
python -m PyInstaller --noconfirm --clean --distpath $distDir --workpath $buildDir $specFile
if ($LASTEXITCODE -ne 0) { throw "ビルドに失敗しました" }

$exePath = Join-Path $distDir "StudyLog\StudyLog.exe"
if (-not (Test-Path $exePath)) { throw "exeが見つかりません: $exePath" }

$size = (Get-ChildItem (Join-Path $distDir "StudyLog") -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ("完成: {0}  ({1:N1} MB)" -f $exePath, $size) -ForegroundColor Green
Write-Host "データは exe と同じフォルダの data\ に作られます。フォルダごと移動できます。"
