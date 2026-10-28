#!/bin/bash
# Package the full AI Trading Lab Data Engine SERVER (mini-services) for Windows
# Includes: web app + trading-engine mini-service + seeded database + deploy scripts
set -e
cd /home/z/my-project

STAGE=/tmp/atl-win-server/AI-Trading-Lab-v4.0-Windows-Server
ZIP=/home/z/my-project/download/AI-Trading-Lab-v4.0-Windows-Server-mini-services.zip

rm -rf /tmp/atl-win-server
mkdir -p "$STAGE"

# ---- source code (server side only) ----
rsync -a --quiet \
  --exclude node_modules --exclude engine.log --exclude .env \
  mini-services/ "$STAGE/mini-services/"

rsync -a --quiet src/ "$STAGE/src/"
rsync -a --quiet prisma/ "$STAGE/prisma/"
rsync -a --quiet --exclude START-HERE-WINDOWS.txt scripts/ "$STAGE/scripts/"
rsync -a --quiet deploy/ "$STAGE/deploy/"
rsync -a --quiet --exclude downloads public/ "$STAGE/public/"

# ---- configs ----
for f in package.json bun.lock next.config.ts tsconfig.json tailwind.config.ts \
         postcss.config.mjs components.json eslint.config.mjs \
         README.md ARCHITECTURE.md .gitignore; do
  [ -f "$f" ] && cp "$f" "$STAGE/"
done

# ---- database (checkpointed, with all seeded data) ----
mkdir -p "$STAGE/db"
python3 -c "
import sqlite3
con = sqlite3.connect('/home/z/my-project/db/custom.db')
con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
con.close()
print('db checkpointed')"
cp db/custom.db "$STAGE/db/custom.db"

# ---- portable env (bat rewrites with absolute path on first run) ----
printf 'DATABASE_URL=file:./db/custom.db\n' > "$STAGE/.env"
printf 'DATABASE_URL=file:./db/custom.db\n' > "$STAGE/mini-services/trading-engine/.env"

# ---- windows quickstart ----
cp scripts/START-HERE-WINDOWS.txt "$STAGE/START-HERE-WINDOWS.txt"

echo "Staged. Contents:"
du -sh "$STAGE" || true

# ---- zip ----
cd /tmp/atl-win-server
rm -f "$ZIP"
zip -r -q "$ZIP" AI-Trading-Lab-v4.0-Windows-Server
cd /home/z/my-project

echo "---- RESULT ----"
ls -lh "$ZIP"
unzip -t "$ZIP" | tail -1
echo "File count: $(unzip -l "$ZIP" | tail -1 | awk '{print $2}')"
