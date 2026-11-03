#!/bin/bash
# v4.4 host-JVM test runner — engine package + tests (android.jar stubs + org.json)
set -e
BASE="$(cd "$(dirname "$0")/.." && pwd)"
JDK=${JDK_BIN:-/usr/lib/jvm/java-21-openjdk-amd64/bin}
AJ=${ANDROID_JAR:-/home/z/android-sdk/platforms/android-34/android.jar}
OUT=/tmp/atl-tests
rm -rf "$OUT" && mkdir -p "$OUT"

echo "=== compiling engine package + tests ==="
"$JDK/javac" -source 17 -target 17 -nowarn \
  -cp "$BASE/engine-tests/org-json.jar:$AJ" \
  -d "$OUT" \
  "$BASE"/android-app/app/src/main/java/com/aitradinglab/engine/*.java \
  "$BASE"/engine-tests/ShaakuniEngineTest.java \
  "$BASE"/engine-tests/V44Test.java \
  "$BASE"/engine-tests/V441Test.java \
  "$BASE"/engine-tests/V442Test.java \
  "$BASE"/engine-tests/V1Test.java 2>&1 | grep -v "^Note:" || true

echo ""
echo "=== ShaakuniEngineTest (v4.1 suite) ==="
"$JDK/java" -cp "$OUT:$BASE/engine-tests/org-json.jar:$AJ" com.aitradinglab.engine.ShaakuniEngineTest || true
echo ""
echo "=== V44Test (v4.4 pack + AI + universe) ==="
"$JDK/java" -cp "$OUT:$BASE/engine-tests/org-json.jar:$AJ" com.aitradinglab.engine.V44Test
echo ""
echo "=== V441Test (v4.4.1 PRO-filter removal guard) ==="
"$JDK/java" -cp "$OUT:$BASE/engine-tests/org-json.jar:$AJ" com.aitradinglab.engine.V441Test
echo ""
echo "=== V442Test (v4.4.2 failover + 5m shift) ==="
"$JDK/java" -cp "$OUT:$BASE/engine-tests/org-json.jar:$AJ" com.aitradinglab.engine.V442Test
echo ""
echo "=== V1Test (v1.0 5M Playbook + persistence guarantee) ==="
"$JDK/java" -cp "$OUT:$BASE/engine-tests/org-json.jar:$AJ" com.aitradinglab.engine.V1Test
