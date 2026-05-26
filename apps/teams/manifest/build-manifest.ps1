param(
    [Parameter(Mandatory=$true)]
    [string]$AppId
)

$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot

$manifest = Get-Content "$dir\manifest.json" -Raw
$manifest = $manifest -replace "YOUR_TEAMS_APP_ID_HERE", $AppId
Set-Content "$dir\manifest.json" $manifest -Encoding UTF8
Write-Host "manifest.json patched with App ID: $AppId"

Add-Type -AssemblyName System.Drawing

function New-SolidPng {
    param([string]$Path, [int]$Width, [int]$Height, [string]$HexColor)
    $bmp = New-Object System.Drawing.Bitmap($Width, $Height)
    $color = [System.Drawing.ColorTranslator]::FromHtml($HexColor)
    for ($x = 0; $x -lt $Width; $x++) {
        for ($y = 0; $y -lt $Height; $y++) {
            $bmp.SetPixel($x, $y, $color)
        }
    }
    $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

$colorPng = "$dir\color.png"
$outlinePng = "$dir\outline.png"

if (-not (Test-Path $colorPng)) {
    New-SolidPng -Path $colorPng -Width 192 -Height 192 -HexColor "#0078D4"
    Write-Host "color.png generated (192x192 blue)"
} else {
    Write-Host "color.png already exists"
}

if (-not (Test-Path $outlinePng)) {
    New-SolidPng -Path $outlinePng -Width 32 -Height 32 -HexColor "#FFFFFF"
    Write-Host "outline.png generated (32x32 white)"
} else {
    Write-Host "outline.png already exists"
}

$zipPath = "$dir\corvin-teams-app.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$dir\manifest.json", $colorPng, $outlinePng -DestinationPath $zipPath
Write-Host "Created: $zipPath"
Write-Host ""
Write-Host "Sideload: Teams -> Apps -> Manage your apps -> Upload a custom app -> select the zip above"
