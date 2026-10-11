#!/bin/sh
# Compile l'application de barre de menu (Xcode et XcodeGen requis) → build/Timebox Bridge.app
set -e
cd "$(dirname "$0")"
command -v xcodegen >/dev/null || { echo "XcodeGen manquant : brew install xcodegen" >&2; exit 1; }
if [ -z "$DEVELOPER_DIR" ] && [ -d /Applications/Xcode.app ]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi
configuration="${CONFIGURATION:-Release}"
xcodegen generate --quiet --spec App/project.yml
xcodebuild -project App/TimeboxBridge.xcodeproj -scheme TimeboxBridge -configuration "$configuration" \
  -destination 'platform=macOS' -derivedDataPath build/dd -quiet build
rm -rf "build/Timebox Bridge.app"
cp -R "build/dd/Build/Products/$configuration/Timebox Bridge.app" build/
echo "ok : $(pwd)/build/Timebox Bridge.app"
