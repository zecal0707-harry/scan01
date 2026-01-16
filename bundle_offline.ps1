$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = $scriptDir
$uiDir = Join-Path $projectRoot "scanner\ui"
$uiDist = Join-Path $uiDir "dist"
$dest = Join-Path $projectRoot "Scanner_Release_Package"
$packagesDir = Join-Path $dest "packages"

Write-Host "=== Starting Offline Bundle Creation ==="

# 1. Check UI Build
Write-Host "`n[1/4] Checking UI Build..."
if (-not (Test-Path $uiDist)) {
    Write-Warning "UI build not found at $uiDist"
    Write-Host "Please run the following commands manually first:"
    Write-Host "  cd scanner/ui"
    Write-Host "  npm install"
    Write-Host "  npm run build"
    Write-Error "UI build missing. Aborting."
}
Write-Host "Found UI build at $uiDist"

# 2. Package Creation (Clean Slate)
Write-Host "`n[2/4] preparing release folder..."
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Path $dest | Out-Null
New-Item -ItemType Directory -Path $packagesDir | Out-Null

# 3. Download Python Dependencies
Write-Host "`n[3/4] Downloading Python dependencies..."
$reqFile = Join-Path $projectRoot "scanner\project\requirements.txt"
# Try root requirements.txt if scanner/project one is missing (adjusting path based on known structure)
if (-not (Test-Path $reqFile)) {
    $reqFile = Join-Path $projectRoot "scanner\requirements.txt"
}
if (-not (Test-Path $reqFile)) {
    $reqFile = Join-Path $projectRoot "requirements.txt" # Try root
}

if (Test-Path $reqFile) {
    Write-Host "Downloading packages from $reqFile to $packagesDir..."
    try {
        pip download -d $packagesDir -r $reqFile
    } catch {
        Write-Warning "pip download failed. Please ensure you have internet connection."
        throw $_
    }
} else {
    Write-Warning "requirements.txt not found. Skipping dependency download."
}

# 4. Copy Project Files
Write-Host "`n[4/4] Copying project files..."
$exclude = @(
    "out",
    "node_modules",
    ".git",
    ".gemini",
    "__pycache__",
    "*.log",
    "*.zip",
    "Scanner_Release_Package",
    "packages" # already handled
)
# Note: "dist" removed from exclude - scanner/ui/dist is needed for UI

function Copy-Filtered {
    param($src, $dst)
    $items = Get-ChildItem -Path $src
    foreach ($item in $items) {
        if ($exclude -contains $item.Name) { continue }
        
        $nextDest = Join-Path $dst $item.Name
        if ($item.PSIsContainer) {
            New-Item -ItemType Directory -Path $nextDest | Out-Null
            Copy-Filtered $item.FullName $nextDest
        } else {
            Copy-Item $item.FullName $nextDest
        }
    }
}

Copy-Filtered $projectRoot $dest

# Copy offline install guide if exists (we will create it next)
# The manual copy above might have missed it if we just created it, but usually it's fine.

Write-Host "`n=== Bundle Complete ==="
Write-Host "Location: $dest"
Write-Host "To install on offline PC:"
Write-Host "1. Copy 'Scanner_Release_Package' folder to target PC."
Write-Host "2. Read 'OFFLINE_INSTALL.md' (creating now...)"
