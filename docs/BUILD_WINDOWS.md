# Building Pdink on Windows

## 1. Requirements

- Windows 10 or Windows 11, x64
- Python 3.13
- Git
- A local Windows Tesseract installation for preparing the runtime directory
- Inno Setup 6 for producing the installer

## 2. Create the environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Prepare Tesseract runtime files

Pdink's release runtime lives under:

```text
runtime\tesseract\
runtime\tesseract\tessdata\
```

Copy a local Windows Tesseract installation into `runtime\tesseract`, then
download the supported language models:

```powershell
New-Item -ItemType Directory -Path ".\runtime\tesseract\tessdata" -Force
Copy-Item "C:\Program Files\Tesseract-OCR\*" ".\runtime\tesseract" -Recurse -Force
powershell -ExecutionPolicy Bypass -File ".\installer\Download-All-Languages.ps1"
```

## 4. Build the portable application folder

```powershell
Remove-Item ".\build", ".\dist", ".\Pdink.spec" -Recurse -Force -ErrorAction SilentlyContinue

python -m PyInstaller --noconfirm --clean --windowed --onedir `
  --contents-directory . `
  --name Pdink `
  --icon ".\assets\Pdink.ico" `
  --add-data "runtime;runtime" `
  --add-data "assets;assets" `
  --collect-all markitdown `
  .\app\main.py
```

Test the result:

```powershell
Start-Process ".\dist\Pdink\Pdink.exe"
```

## 5. Build the installer

Install Inno Setup 6, then compile the installer script:

```powershell
& "C:\Program Files\Inno Setup 6\ISCC.exe" ".\installer\Pdink_installer.iss"
```

The installer is produced in `release/`.

## Notes

- `runtime/`, `build/`, `dist/`, and `release/` are excluded from Git.
- The GitHub repository contains the source and build instructions.
- The compiled installer belongs in a GitHub Release, not in the Git source tree.
