#!/usr/bin/env bash
# Drive the spider runtime: one JSON request per line on stdin, JSON responses on stdout.
# usage: JAR=/path/spider.jar run.sh '{"id":1,"api":"csp_AppRJ","ext":"...","method":"homeContent","args":[true]}' ...
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

LIB="${LIB:-$HERE/lib}"
JAR="${JAR:?set JAR to the converted spider jar}"
DATA="${DATA:-$HERE/../data/spider}"
mkdir -p "$DATA/out"
[ -d build/classes ] || bash build.sh

if [ "$#" -gt 0 ]; then
  REQ=$(printf '%s\n' "$@")
else
  REQ=$(cat)
fi

java -Xverify:none -Xmx"${SPIDER_JVM_XMX:-512m}" -cp "build/classes:$LIB/*" \
     -Dspider.data.dir="$DATA" -Dspider.out.dir="$DATA/out" \
     -Dspider.jar="$JAR" -Dspider.lib.dir="$LIB" \
     -Dfile.encoding=UTF-8 \
     com.docktvbox.spider.Runner <<<"$REQ"
