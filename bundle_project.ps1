$source = "d:\code\scanner\FTP_DN_PRJ_gemini"
$dest = "d:\code\scanner\FTP_DN_PRJ_gemini\Scanner_Release_Package"
$exclude = @(
    "out", 
    "node_modules", 
    "dist", 
    ".git", 
    ".gemini", 
    "__pycache__", 
    "*.log", 
    "*.zip", 
    "Scanner_Release_Package"
)

Write-Host "Creating Release Package at $dest..."
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Path $dest | Out-Null

# Function to copy with exclusion
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

Copy-Filtered $source $dest

Write-Host "Done. You can now copy the '$dest' folder to the new computer."
Write-Host "Ensure to check DEPLOY.md inside it."
