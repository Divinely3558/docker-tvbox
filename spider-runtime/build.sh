#!/usr/bin/env bash
# Build the dex->JVM spider runtime: android/catvod shim + runner.
set -euo pipefail
cd "$(dirname "$0")"

LIB="${LIB:-$([ -d "$PWD/lib" ] && echo "$PWD/lib" || echo "$HOME/tools/spike/lib")}"
OUT=build/classes

rm -rf "$OUT"
mkdir -p "$OUT"

python3 gen_stubs.py

CP=$(ls "$LIB"/*.jar | tr '\n' ':')
javac -nowarn -encoding UTF-8 -cp "$CP" -d "$OUT" $(find shim runner -name '*.java')
echo "built $(find "$OUT" -name '*.class' | wc -l) classes -> $OUT"
