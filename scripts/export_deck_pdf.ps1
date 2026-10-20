param(
    [string]$Pptx = "deliverables\INDmoney_SIP_Discovery_Deck.pptx",
    [string]$Pdf = "deliverables\INDmoney_SIP_Discovery_Deck.pdf"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pptxPath = [System.IO.Path]::GetFullPath((Join-Path $root $Pptx))
$pdfPath = [System.IO.Path]::GetFullPath((Join-Path $root $Pdf))

if (-not (Test-Path $pptxPath)) {
    throw "Deck not found: $pptxPath"
}

$powerPoint = $null
$presentation = $null
try {
    $powerPoint = New-Object -ComObject PowerPoint.Application
    $presentation = $powerPoint.Presentations.Open($pptxPath, $true, $false, $false)
    # 32 = ppSaveAsPDF
    $presentation.SaveAs($pdfPath, 32)
    Write-Output "Exported $pdfPath"
}
finally {
    if ($presentation -ne $null) { $presentation.Close() }
    if ($powerPoint -ne $null) { $powerPoint.Quit() }
}
