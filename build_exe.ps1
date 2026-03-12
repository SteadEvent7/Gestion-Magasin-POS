$ErrorActionPreference = 'Stop'

# Build one-file Windows executable.
$python = ".venv/Scripts/python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python -m PyInstaller --noconfirm --clean --onefile --name GestionMagasinPOS --add-data "schema_mysql.sql;." --add-data "schema_sqlite.sql;." run.py
Write-Host "Build termine. Binaire: dist/GestionMagasinPOS.exe"
