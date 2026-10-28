#!/bin/bash
# Build v5.9 Android source zip (excludes build/, .gradle/, local.properties)
set -e
cd /home/z/my-project
OUT_DL="download/AI-Trading-Lab-v5.9-Android-source.zip"
OUT_PUB="public/downloads/AI-Trading-Lab-v5.9-Android-source.zip"
cd android-app
rm -f "/home/z/my-project/$OUT_DL" "/home/z/my-project/$OUT_PUB"
zip -r "/home/z/my-project/$OUT_DL" . \
  -x "app/build/*" -x ".gradle/*" -x "local.properties" -x "*.iml" -x ".idea/*" \
  | tail -2
cd /home/z/my-project
cp "$OUT_DL" "$OUT_PUB"
echo "--- contents check ---"
unzip -l "$OUT_DL" | tail -5
echo "--- java files ---"
unzip -l "$OUT_DL" | rg "\.java|dashboard.html|build.gradle|AndroidManifest" | head -12
