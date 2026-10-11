#!/bin/sh
# Compile la ligne de commande timebox-bridge (les outils en ligne de commande d'Xcode suffisent).
# L'Info.plist intégré (déclaration d'usage du Bluetooth) est ajouté par Package.swift.
set -e
cd "$(dirname "$0")"
swift build -c release --product timebox-bridge
mkdir -p build
cp "$(swift build -c release --show-bin-path)/timebox-bridge" build/
echo "ok : $(pwd)/build/timebox-bridge"
