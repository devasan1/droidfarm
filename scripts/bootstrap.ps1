#Requires -Version 5.1
<#
.SYNOPSIS
  DroidFarm single-click bootstrap: installs dependencies, builds the app,
  and launches the desktop UI.

.NOTES
  Runs from DroidFarm.bat. Safe to re-run; every step is idempotent.
  Steps that need admin (winget, LDPlayer install) self-elevate via UAC.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

$repoRoot    = Split-Path -Parent $PSScriptRoot
$stateRoot   = Join-Path $env:LOCALAPPDATA 'DroidFarm'
$logFile     = Join-Path $stateRoot 'bootstrap.log'
$venvDir     = Join-Path $repoRoot 'backend\.venv'
$pythonExe   = Join-Path $venvDir 'Scripts\python.exe'
$frontendDir = Join-Path $repoRoot 'frontend'
$distDir     = Join-Path $frontendDir 'dist'

New-Item -ItemType Directory -Force $stateRoot | Out-Null

function Log([string]$msg) {
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line  = "[$stamp] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

function Have-Cmd([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Ensure-Winget {
    if (Have-Cmd winget) { return }
    Log 'winget not found. Install "App Installer" from the Microsoft Store and rerun DroidFarm.bat.'
    Start-Process 'ms-windows-store://pdp/?productid=9NBLGGH4NNS1'
    throw 'winget missing'
}

function Winget-Install([string]$id, [string]$friendly) {
    Log "installing $friendly ($id) via winget"
    $args = @(
        'install','--id', $id,
        '--silent','--accept-package-agreements','--accept-source-agreements',
        '--source','winget'
    )
    & winget @args | Tee-Object -FilePath $logFile -Append | Out-Null
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {
        # -1978335189 == already installed; fine.
        Log "winget exited $LASTEXITCODE for $id (continuing)"
    }
}

function Refresh-Path {
    # winget installers add to PATH in HKLM/HKCU but our session doesn't see it
    # until we reload. Merge machine + user env PATH into the current session.
    $machine = [Environment]::GetEnvironmentVariable('Path','Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = "$machine;$user"
}

function Ensure-Python {
    if (Have-Cmd py) {
        try { & py -3.11 -V | Out-Null; return } catch {}
    }
    if (Have-Cmd python) {
        $v = & python -V 2>&1
        if ($v -match '3\.(1[0-2])') { return }
    }
    Ensure-Winget
    Winget-Install 'Python.Python.3.11' 'Python 3.11'
    Refresh-Path
    if (-not (Have-Cmd python) -and -not (Have-Cmd py)) {
        throw 'Python installation did not land on PATH; open a new terminal and rerun.'
    }
}

function Ensure-Node {
    if (Have-Cmd node) {
        $v = & node -v
        if ($v -match 'v(1[89]|2[0-9])') { return }
    }
    Ensure-Winget
    Winget-Install 'OpenJS.NodeJS.LTS' 'Node.js LTS'
    Refresh-Path
    if (-not (Have-Cmd node)) { throw 'Node.js installation failed; rerun DroidFarm.bat' }
}

function Ensure-Git {
    if (Have-Cmd git) { return }
    Ensure-Winget
    Winget-Install 'Git.Git' 'Git'
    Refresh-Path
}

function Ensure-LDPlayer {
    $defaultPath = 'C:\LDPlayer\LDPlayer9\ldconsole.exe'
    if (Test-Path $defaultPath) {
        Log "LDPlayer found at $defaultPath"
        return
    }
    Log 'LDPlayer 9 not found; downloading installer...'
    $installer = Join-Path $env:TEMP 'ldplayer9.exe'
    try {
        Invoke-WebRequest 'https://res.ldrescdn.com/download/package/LDPlayer9.exe' -OutFile $installer
    } catch {
        Log "LDPlayer download failed: $_"
        throw
    }
    Log 'running LDPlayer installer silently — this may take ~2 min and prompt UAC'
    Start-Process -FilePath $installer -ArgumentList '/S' -Verb RunAs -Wait
    if (-not (Test-Path $defaultPath)) {
        Log 'LDPlayer installer finished but ldconsole.exe still missing — skipping; DroidFarm will run in mock mode until you install LDPlayer.'
    }
}

function Get-Python {
    if (Test-Path $pythonExe) { return $pythonExe }
    if (Have-Cmd py) { return 'py' }
    if (Have-Cmd python) { return 'python' }
    throw 'no python found'
}

function Ensure-Venv {
    if (Test-Path $pythonExe) { return }
    Log 'creating Python venv at backend\.venv'
    $bootstrapPy = Get-Python
    if ($bootstrapPy -eq 'py') {
        & py -3.11 -m venv $venvDir
    } else {
        & $bootstrapPy -m venv $venvDir
    }
}

function Install-Backend {
    Log 'installing backend dependencies (pip install -e backend)'
    & $pythonExe -m pip install --upgrade pip --quiet
    & $pythonExe -m pip install -e (Join-Path $repoRoot 'backend') --quiet
}

function Ensure-Frontend-Built {
    if (Test-Path (Join-Path $distDir 'index.html')) { return }
    if (-not (Test-Path (Join-Path $frontendDir 'package.json'))) {
        Log 'frontend/package.json missing — skipping frontend build (backend-only mode)'
        return
    }
    Log 'installing frontend deps (npm install)'
    Push-Location $frontendDir
    try {
        & npm install --silent
        Log 'building frontend (npm run build)'
        & npm run build --silent
    } finally { Pop-Location }
}

function Ensure-HostAutostart {
    # Drop a .lnk into the user's Startup folder so DroidFarm.bat runs on
    # every login — phones marked autostart=True then auto-resume via the
    # backend's resume-autostart-phones boot hook. Idempotent.
    $startup = [Environment]::GetFolderPath('Startup')
    $lnk     = Join-Path $startup 'DroidFarm.lnk'
    $target  = Join-Path $repoRoot 'DroidFarm.bat'
    if (Test-Path $lnk) {
        Log "host autostart already configured ($lnk)"
        return
    }
    try {
        $ws = New-Object -ComObject WScript.Shell
        $s  = $ws.CreateShortcut($lnk)
        $s.TargetPath       = $target
        $s.WorkingDirectory = $repoRoot
        $s.WindowStyle      = 7   # minimized
        $s.Description      = 'DroidFarm — local Android farm control plane'
        $s.Save()
        Log "host autostart installed: $lnk"
    } catch {
        Log "host autostart install failed (non-fatal): $_"
    }
}

function Launch-App {
    Log 'starting DroidFarm backend on http://127.0.0.1:7870'
    $env:DROIDFARM_HOST = '127.0.0.1'
    $env:DROIDFARM_PORT = '7870'
    # Start the backend as a hidden background process and open the UI in the
    # default browser. When the Tauri shell lands (commit 10), we swap this
    # for a single .exe launch.
    Start-Process -WindowStyle Hidden -FilePath $pythonExe `
        -ArgumentList '-m','droidfarm.main'
    Start-Sleep -Seconds 2
    Start-Process 'http://127.0.0.1:7870'
    Log 'DroidFarm launched. UI will open in your default browser.'
    Log "backend logs: $stateRoot\bootstrap.log"
}

# -------------------------- run --------------------------

Log "---- DroidFarm bootstrap starting ($repoRoot) ----"

try {
    Ensure-Python
    Ensure-Node
    Ensure-Git
    Ensure-LDPlayer
    Ensure-Venv
    Install-Backend
    Ensure-Frontend-Built
    Ensure-HostAutostart
    Launch-App
} catch {
    Log "FAILED: $_"
    Write-Host ''
    Write-Host 'DroidFarm bootstrap failed:' -ForegroundColor Red
    Write-Host $_ -ForegroundColor Red
    Write-Host "See $logFile for the full transcript."
    exit 1
}
