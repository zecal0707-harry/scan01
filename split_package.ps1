$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Configuration
$sourceDir = Join-Path $scriptDir "Scanner_Release_Package"
$zipFile = Join-Path $scriptDir "scanner_pkg.zip"
$chunkSize = 9MB

if (-not (Test-Path $sourceDir)) {
    Write-Error "Scanner_Release_Package not found. Please run bundle_offline.ps1 first."
}

# 1. Zip the package
Write-Host "Compressing $sourceDir to $zipFile..."
if (Test-Path $zipFile) { Remove-Item $zipFile -Force }
Compress-Archive -Path "$sourceDir\*" -DestinationPath $zipFile -Force

# 2. Split the zip
Write-Host "Splitting into chunks (Max $(($chunkSize/1MB))MB)..."
$inputStream = [System.IO.File]::OpenRead($zipFile)
$buffer = New-Object byte[] $chunkSize
$partNumber = 1

try {
    while ($true) {
        $bytesRead = $inputStream.Read($buffer, 0, $buffer.Length)
        if ($bytesRead -eq 0) { break }
        
        $partName = "$zipFile.{0:D3}" -f $partNumber
        $outputConfig = [System.IO.FileMode]::Create
        $outputStream = [System.IO.File]::Open($partName, $outputConfig)
        try {
            $outputStream.Write($buffer, 0, $bytesRead)
        }
        finally {
            $outputStream.Close()
        }
        
        Write-Host "Created $partName ($(($bytesRead/1KB).ToString("N0")) KB)"
        $partNumber++
    }
}
finally {
    $inputStream.Close()
}

# 3. Create Merge Script (Batch)
$mergeBat = Join-Path $scriptDir "merge_package.bat"
$baseName = Split-Path $zipFile -Leaf
Set-Content -Path $mergeBat -Value "@echo off
echo Merging parts...
copy /b ${baseName}.* ${baseName}
echo Done. You can now unzip ${baseName}
pause"

Write-Host "`n=== Split Complete ==="
Write-Host "Generated files:"
Get-ChildItem -Path "$zipFile.*" | ForEach-Object { Write-Host " - $($_.Name)" }
Write-Host "`nTo transfer:"
Write-Host "1. Email the generated .001, .002... files and 'merge_package.bat' separately."
Write-Host "2. On target PC, put all files in one folder."
Write-Host "3. Run 'merge_package.bat'."
Write-Host "4. Unzip 'scanner_pkg.zip'."
