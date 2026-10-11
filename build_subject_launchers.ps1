param(
    [string]$Exe = "dist\StudyTracker\StudyTracker.exe",
    [string]$Destination = "dist\StudyTracker\MTCApps"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $Exe)) {
    throw "StudyTracker.exe が見つかりません。先にbuild_windows.ps1を実行してください。"
}

$python = Get-Command python -ErrorAction Stop
$script = Join-Path $PSScriptRoot "tools\create_subject_launchers.py"
& $python.Source $script --db "$env:USERPROFILE\StudyTracker\study_tracker.sqlite3" --exe $Exe --destination $Destination
