# Downloads the full official Tesseract tessdata_fast language set into Pdink.
# Run from the Pdink project root:
#   powershell -ExecutionPolicy Bypass -File .\installer\Download-All-Languages.ps1

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $projectRoot "runtime\tesseract\tessdata"

New-Item -ItemType Directory -Path $target -Force | Out-Null

$headers = @{
    "User-Agent" = "Pdink-Language-Pack-Setup"
    "Accept"     = "application/vnd.github+json"
}

Write-Host "Getting the official Tesseract language-pack list..." -ForegroundColor Cyan

$items = Invoke-RestMethod `
    -Uri "https://api.github.com/repos/tesseract-ocr/tessdata_fast/contents" `
    -Headers $headers

$models = @(
    $items | Where-Object {
        $_.type -eq "file" -and $_.name -like "*.traineddata"
    } | Sort-Object name
)

if ($models.Count -eq 0) {
    throw "No language-pack files were returned by the official repository."
}

$total = $models.Count
$index = 0

foreach ($model in $models) {
    $index++
    $destination = Join-Path $target $model.name

    $needsDownload = $true
    if (Test-Path $destination) {
        $existingSize = (Get-Item $destination).Length
        if ($existingSize -eq $model.size) {
            $needsDownload = $false
        }
    }

    if ($needsDownload) {
        Write-Progress `
            -Activity "Downloading Pdink OCR languages" `
            -Status "$index of $total — $($model.name)" `
            -PercentComplete (($index / $total) * 100)

        Invoke-WebRequest `
            -Uri $model.download_url `
            -Headers @{ "User-Agent" = "Pdink-Language-Pack-Setup" } `
            -OutFile $destination
    }
    else {
        Write-Host "Keeping existing: $($model.name)" -ForegroundColor DarkGray
    }
}

Write-Progress -Activity "Downloading Pdink OCR languages" -Completed

$count = (Get-ChildItem $target -Filter "*.traineddata").Count
Write-Host ""
Write-Host "Done. Pdink now contains $count official Tesseract language/data packs." -ForegroundColor Green
Write-Host "Location: $target"
