#!/bin/bash
# Sync data from Mac Mini

REMOTE="mac-mini:/Users/moonvision/autoWriteAgent/data/"
LOCAL="$(dirname "$0")/../data/"

echo "Syncing from Mac Mini..."
rsync -avz -e ssh "$REMOTE" "$LOCAL"
echo "Done. $(sqlite3 "$LOCAL/autowrite.db" "SELECT COUNT(*) FROM ideas;") ideas, $(sqlite3 "$LOCAL/autowrite.db" "SELECT COUNT(*) FROM contents;") contents, $(sqlite3 "$LOCAL/autowrite.db" "SELECT COUNT(*) FROM publications;") publications."
