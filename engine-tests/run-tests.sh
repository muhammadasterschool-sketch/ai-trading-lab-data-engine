#!/bin/bash
# v4.4 host-JVM test runner — engine package + tests (android.jar stubs + org.json)
set -e
BASE="$(cd "$(dirname "$0")/.." && pwd)"
JDK=/home/z/my-project/tools/jdk/bin
AJ=/home/z/my-project/tools/android-sdk/platforms/android-34/android.jar
OUT=/tmp/atl-tests
rm -rf "$OUT" && mkdir -p "$OUT"

echo "=== compiling engine package + tests ==="
"$JDK/javac" -source 17 -target 17 -nowarn \
  -cp "$BASE/engine-tests/org-json.jar:$AJ" \
  -d "$OUT" \
  "$BASE"/android-app/app/src/main/java/com/aitradinglab/engine/*.java \
  "$BASE"/engine-tests/ShaakuniEngineTest.java \
  "$BASE"/engine-tests/V44Test.java 2>&1 | grep -v "^Note:" || true

echo ""
echo "=== ShaakuniEngineTest (v4.1 suite) ==="
"$JDK/java" -cp "$OUT:$BASE/engine-tests/org-json.jar:$AJ" com.aitradinglab.engine.ShaakuniEngineTest || true
echo ""
echo "=== V44Test (v4.4 pack + AI + universe) ==="
"$JDK/java" -cp "$OUT:$BASE/engine-tests/org-json.jar:$AJ" com.aitradinglab.engine.V44Test
