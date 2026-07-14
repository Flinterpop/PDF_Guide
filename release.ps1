<#
Release PDF Sherpa: bump the version in app.py + installer.iss, build the
one-file exe, the installer, and the portable zip, commit and push the bump,
publish a GitHub release with both assets, then reinstall locally.

Usage:
  .\release.ps1 1.3.8
  .\release.ps1 1.3.8 -NotesFile notes.md      # release notes from a file
  .\release.ps1 1.3.8 -Notes "- fixed X"       # inline release notes
  .\release.ps1 1.3.8 -SkipInstall             # don't reinstall/relaunch here

Without -Notes/-NotesFile the GitHub notes are auto-generated from commits.
Requires: python (with PyInstaller), Inno Setup 6, gh (authenticated), git.
Windows PowerShell 5.1 compatible.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [string]$Notes = "",
    [string]$NotesFile = "",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }
function CheckExit($what) {
    if ($LASTEXITCODE -ne 0) { Fail "$what failed (exit $LASTEXITCODE)" }
}

# --- Preflight ---------------------------------------------------------------
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source } else { Fail "ISCC.exe not found (Inno Setup 6)" }
}
foreach ($tool in "python", "git", "gh") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail "$tool not on PATH" }
}
if ($NotesFile -and -not (Test-Path $NotesFile)) { Fail "notes file not found: $NotesFile" }

$dirty = git status --porcelain
if ($dirty) { Fail "working tree not clean -- commit or stash first:`n$dirty" }

# --- Bump versions -----------------------------------------------------------
Write-Host "==> Bumping version to $Version" -ForegroundColor Cyan
$appPy = Join-Path $PSScriptRoot "app.py"
$iss   = Join-Path $PSScriptRoot "installer.iss"

$text = [IO.File]::ReadAllText($appPy)
if ($text -notmatch 'APP_VERSION = "[^"]+"') { Fail "APP_VERSION line not found in app.py" }
[IO.File]::WriteAllText($appPy, ($text -replace 'APP_VERSION = "[^"]+"', "APP_VERSION = `"$Version`""))

$text = [IO.File]::ReadAllText($iss)
if ($text -notmatch '#define AppVersion "[^"]+"') { Fail "AppVersion line not found in installer.iss" }
[IO.File]::WriteAllText($iss, ($text -replace '#define AppVersion "[^"]+"', "#define AppVersion `"$Version`""))

# --- Build -------------------------------------------------------------------
try { Stop-Process -Name PDFSherpa -Force -Confirm:$false -ErrorAction Stop
      Write-Host "==> Stopped running PDF Sherpa" -ForegroundColor Cyan } catch {}

Write-Host "==> Building exe (PyInstaller)" -ForegroundColor Cyan
python -m PyInstaller PDFSherpa.spec --noconfirm
CheckExit "PyInstaller"

Write-Host "==> Building installer (ISCC)" -ForegroundColor Cyan
& $iscc installer.iss
CheckExit "ISCC"

Write-Host "==> Building portable zip" -ForegroundColor Cyan
Compress-Archive -Force -Path dist\PDFSherpa.exe -DestinationPath installer\PDFSherpa-Portable.zip

# Both asset names are load-bearing: the in-app updater matches them exactly.
foreach ($asset in "installer\PDFSherpa-Setup.exe", "installer\PDFSherpa-Portable.zip") {
    if (-not (Test-Path $asset)) { Fail "expected artifact missing: $asset" }
}

# --- Commit + push -----------------------------------------------------------
git add app.py installer.iss
$staged = git diff --cached --name-only
if ($staged) {
    git commit -m "Bump version to $Version"
    CheckExit "git commit"
} else {
    Write-Host "==> Versions already at $Version, nothing to commit" -ForegroundColor Yellow
}

Write-Host "==> Syncing with origin (README is sometimes edited on the web)" -ForegroundColor Cyan
git pull --rebase origin main
CheckExit "git pull --rebase"
git push origin main
CheckExit "git push"

# --- Publish release ---------------------------------------------------------
Write-Host "==> Publishing GitHub release v$Version" -ForegroundColor Cyan
$ghArgs = @("release", "create", "v$Version",
            "installer\PDFSherpa-Setup.exe", "installer\PDFSherpa-Portable.zip",
            "--title", "v$Version")
if ($NotesFile)  { $ghArgs += @("--notes-file", $NotesFile) }
elseif ($Notes)  { $ghArgs += @("--notes", $Notes) }
else             { $ghArgs += "--generate-notes" }
& gh @ghArgs
CheckExit "gh release create"

# --- Local reinstall ---------------------------------------------------------
if (-not $SkipInstall) {
    Write-Host "==> Reinstalling locally and relaunching" -ForegroundColor Cyan
    Start-Process (Join-Path $PSScriptRoot "installer\PDFSherpa-Setup.exe") `
        -ArgumentList "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES" -Wait
    Start-Process "$env:LOCALAPPDATA\Programs\PDF Sherpa\PDFSherpa.exe"
}

Write-Host "==> Done: https://github.com/Flinterpop/PDF_Sherpa/releases/tag/v$Version" -ForegroundColor Green
