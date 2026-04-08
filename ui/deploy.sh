#!/bin/bash
# Deploy UI to Mac Mini as a user service (launchd)
# launchd runs as the logged-in user → has Keychain access → claude works

cd "$(dirname "$0")"

REMOTE="mac-mini"
REMOTE_DIR="/Users/moonvision/autoWriteAgent/ui"
PLIST_NAME="com.autowrite.ui"
PLIST_DEST="/Users/moonvision/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "1. Building frontend..."
cd frontend
npm run build 2>&1 | tail -3
cd ..

echo "2. Syncing to Mac Mini..."
rsync -avz --quiet -e ssh backend/ $REMOTE:$REMOTE_DIR/backend/
rsync -avz --quiet -e ssh frontend/dist/ $REMOTE:$REMOTE_DIR/frontend/dist/
scp -q com.autowrite.ui.plist $REMOTE:$PLIST_DEST

echo "3. Restarting service..."
ssh $REMOTE "launchctl unload $PLIST_DEST 2>/dev/null; launchctl load $PLIST_DEST"
sleep 2

# Verify
MINI_IP=$(ssh $REMOTE "ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null")
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://$MINI_IP:8795 2>/dev/null)

echo ""
if [ "$STATUS" = "200" ]; then
  echo "  Deployed!"
  echo "  Access: http://$MINI_IP:8795"
else
  echo "  Service starting... check logs if not ready:"
fi
echo "  Logs: ssh mac-mini 'tail -f /tmp/autowrite-ui.log'"
echo "  Stop: ssh mac-mini 'launchctl unload $PLIST_DEST'"
echo ""
