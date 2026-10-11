#!/bin/sh
# Lance les tests du cœur (Swift Testing). Utilise Xcode s'il est installé ; sinon les outils en
# ligne de commande, en indiquant où se trouve Testing.framework (que SwiftPM n'y trouve pas seul).
set -e
cd "$(dirname "$0")"
xcode=/Applications/Xcode.app/Contents/Developer
if [ -z "$DEVELOPER_DIR" ] && [ -d "$xcode" ]; then
  export DEVELOPER_DIR="$xcode"
fi
dev="${DEVELOPER_DIR:-$(xcode-select -p)}"
case "$dev" in
  *CommandLineTools*)
    fw="$dev/Library/Developer/Frameworks"
    lib="$dev/Library/Developer/usr/lib"
    exec swift test -Xswiftc -F -Xswiftc "$fw" -Xlinker -F -Xlinker "$fw" \
      -Xlinker -rpath -Xlinker "$fw" -Xlinker -rpath -Xlinker "$lib" "$@"
    ;;
  *)
    exec swift test "$@"
    ;;
esac
