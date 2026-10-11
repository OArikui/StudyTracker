$ErrorActionPreference = "Stop"
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name StudyTracker main.py
Write-Host "dist\StudyTracker\StudyTracker.exe"
