#!/usr/bin/env bash
# Build the dex->JVM spider runtime: android/catvod shim + runner.
set -euo pipefail
cd "$(dirname "$0")"

LIB="${LIB:-$([ -d "$PWD/lib" ] && echo "$PWD/lib" || echo "$HOME/tools/spike/lib")}"
OUT=build/classes

rm -rf "$OUT"
mkdir -p "$OUT"

python3 gen_stubs.py

# d2j 提供 ASM：ElfAgent（织入 Runtime.load0）与 AsmFix（重算 stackmap）编译要用
CP=$(ls "$LIB"/*.jar d2j/*.jar | tr '\n' ':')
javac -nowarn -encoding UTF-8 -cp "$CP" -d "$OUT" $(find shim runner -name '*.java')
echo "built $(find "$OUT" -name '*.class' | wc -l) classes -> $OUT"

# 加固 jar 解包的 -javaagent：elfagent.jar 织入 Runtime.load0，在 dlopen 前修补
# 运行期才释放的 bionic .so；elfpatch.jar 只含 ElfPatch，由 agent 追加进 bootstrap
# classpath 供被织入的 JDK 类引用（混在一个 jar 会造成类加载器分裂）
MANIFEST="$(mktemp)"
printf 'Manifest-Version: 1.0\nPremain-Class: com.docktvbox.spider.ElfAgent\nCan-Retransform-Classes: true\n' >"$MANIFEST"
( cd "$OUT" && jar cfm ../../runner/elfagent.jar "$MANIFEST" com/docktvbox/spider/ElfAgent*.class )
( cd "$OUT" && jar cf ../../runner/elfpatch.jar com/docktvbox/spider/ElfPatch.class )
rm -f "$MANIFEST"
echo "packed runner/elfagent.jar + runner/elfpatch.jar"
