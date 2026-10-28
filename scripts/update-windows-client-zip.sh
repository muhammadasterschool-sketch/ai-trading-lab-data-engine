#!/bin/bash
# Update the Windows CLIENT zip with the new connect.html (Local/Cloud picker)
set -e
cd /home/z/my-project
STAGE=/tmp/atl-win-client
ZIP_IN=download/AI-Trading-Lab-v4.0-Windows.zip

rm -rf "$STAGE"
mkdir -p "$STAGE"
echo "[1/3] Extracting existing Windows client zip..."
unzip -q "$ZIP_IN" -d "$STAGE"

echo "[2/3] Replacing connect.html with Local/Cloud picker version..."
cp windows-app/connect.html "$STAGE/AI-Trading-Lab-v4.0-Windows/resources/app/connect.html"

echo "[3/3] Re-zipping..."
cd "$STAGE"
rm -f /home/z/my-project/download/AI-Trading-Lab-v4.0-Windows.zip
zip -r -q /home/z/my-project/download/AI-Trading-Lab-v4.0-Windows.zip AI-Trading-Lab-v4.0-Windows
cd /home/z/my-project

echo "---- VERIFY ----"
unzip -l download/AI-Trading-Lab-v4.0-Windows.zip | grep -E "connect.html|AI Trading Lab.exe" | head -3
unzip -t download/AI-Trading-Lab-v4.0-Windows.zip | tail -1
unzip -p download/AI-Trading-Lab-v4.0-Windows.zip "AI-Trading-Lab-v4.0-Windows/resources/app/connect.html" | grep -c "modeLocal\|modeCloud" && echo "Local/Cloud picker INSIDE zip: OK"
ls -lh download/AI-Trading-Lab-v4.0-Windows.zip
