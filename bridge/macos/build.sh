#!/bin/sh
# Compile timebox-bridge avec un Info.plist intégré (déclaration d'usage du Bluetooth exigée par macOS).
set -e
cd "$(dirname "$0")"
swiftc -O main.swift -o timebox-bridge \
  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker Info.plist
echo "ok : $(pwd)/timebox-bridge"
