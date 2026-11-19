#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
publish_dir="$root_dir/publish"
installer_dir="$root_dir/installer-output"

dotnet publish "$root_dir/VisionAgent.csproj" \
  --configuration Release \
  --runtime win-x64 \
  --self-contained true \
  --output "$publish_dir" \
  -p:PublishSingleFile=true \
  -p:IncludeNativeLibrariesForSelfExtract=true

mkdir -p "$installer_dir"
makensis \
  "-DAPP_EXE=$publish_dir/VisionAgent.exe" \
  "-DAPP_ICON=$root_dir/Assets/vision-agent.ico" \
  "-DOUTPUT_EXE=$installer_dir/VisionAgent-Setup.exe" \
  "$root_dir/installer/VisionAgent.nsi"
