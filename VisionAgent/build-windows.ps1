$ErrorActionPreference = "Stop"
$project = Join-Path $PSScriptRoot "VisionAgent.csproj"
$publishDir = Join-Path $PSScriptRoot "publish"

dotnet publish $project `
  --configuration Release `
  --runtime win-x64 `
  --self-contained true `
  --output $publishDir `
  -p:PublishSingleFile=true `
  -p:IncludeNativeLibrariesForSelfExtract=true

if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed with exit code $LASTEXITCODE" }

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($iscc) {
  & $iscc.Source (Join-Path $PSScriptRoot "installer\VisionAgent.iss")
  if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed with exit code $LASTEXITCODE" }
} else {
  $makensis = Get-Command makensis.exe -ErrorAction SilentlyContinue
  if ($makensis) {
    $installerDir = Join-Path $PSScriptRoot "installer-output"
    New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
    & $makensis.Source "-DAPP_EXE=$publishDir\VisionAgent.exe" "-DAPP_ICON=$PSScriptRoot\Assets\vision-agent.ico" "-DOUTPUT_EXE=$installerDir\VisionAgent-Setup.exe" (Join-Path $PSScriptRoot "installer\VisionAgent.nsi")
    if ($LASTEXITCODE -ne 0) { throw "NSIS compilation failed with exit code $LASTEXITCODE" }
  } else {
    Write-Host "App published to $publishDir. Install Inno Setup 6 or NSIS to create VisionAgent-Setup.exe."
  }
}
