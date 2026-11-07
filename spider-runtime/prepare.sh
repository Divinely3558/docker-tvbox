#!/usr/bin/env bash
# Fetch/convert the JVM side of the spider runtime.
#   prepare.sh deps                      -> maven copy-dependencies into spider-runtime/lib
#   prepare.sh convert <jar|apk> [name]  -> dex2jar into spider-runtime/spiders/<name>.jar
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
D2J="${D2J:-$HERE/d2j}"
SPIDERS="${SPIDERS:-$HERE/spiders}"
MVN="${MVN:-mvn}"

case "${1:-}" in
  deps)
    mkdir -p "$HERE/lib"
    "$MVN" -q -f "$HERE/deps.xml" dependency:copy-dependencies "-DoutputDirectory=$HERE/lib"
    ls "$HERE/lib"
    ;;
  convert)
    src="${2:?usage: prepare.sh convert <jar-or-apk> [name]}"
    out="${3:-$(basename "${src%.*}")}"
    mkdir -p "$SPIDERS"
    if unzip -l "$src" classes.dex >/dev/null 2>&1 || [[ "$(head -c 4 "$src" 2>/dev/null | od -An -c | tr -d ' \n')" == *dex* ]]; then
      tmp="$(mktemp -d)"
      mkdir -p "$tmp/x"
      (cd "$tmp/x" && unzip -oq "$src" classes.dex && chmod 644 classes.dex)
      # dex2jar always fails on one or two obfuscated classes; the rest of the jar is still emitted.
      java -Xmx"${D2J_XMX:-2g}" -cp "$D2J/*" com.googlecode.dex2jar.tools.Dex2jarCmd -f \
           -o "$SPIDERS/$out.jar" "$tmp/x/classes.dex" || true
      rm -rf "$tmp"
    else
      cp "$src" "$SPIDERS/$out.jar"   # already a JVM jar
    fi
    printf '%s -> %s (%s classes)\n' "$src" "$SPIDERS/$out.jar" \
      "$(unzip -l "$SPIDERS/$out.jar" | grep -c '\.class$')"
    ;;
  *)
    sed -n '2,5p' "$0"
    exit 1
    ;;
esac
