#!/bin/bash
# Backend runs on Mac Mini (direct DB access), frontend runs locally

cd "$(dirname "$0")"

REMOTE_BACKEND="mac-mini"
REMOTE_DIR="/Users/moonvision/autoWriteAgent/ui/backend"

cleanup() {
  echo "Stopping..."
  kill $TUNNEL_PID $FRONTEND_PID 2>/dev/null
  # Kill remote uvicorn
  ssh $REMOTE_BACKEND "pkill -f 'uvicorn main:app.*--port 8000'" 2>/dev/null
  exit 0
}
trap cleanup INT TERM

# Sync backend code to Mac Mini
echo "Syncing backend code to Mac Mini..."
rsync -avz --quiet -e ssh backend/ $REMOTE_BACKEND:$REMOTE_DIR/

# Start backend on Mac Mini with SSH port forwarding
echo "Starting backend on Mac Mini (port-forwarded to localhost:8000)..."
ssh -L 8000:localhost:8000 $REMOTE_BACKEND \
  "cd $REMOTE_DIR && /usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8000" &
TUNNEL_PID=$!
sleep 3

# Start frontend locally
echo "Starting frontend on http://localhost:5173 ..."
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend:  Mac Mini -> localhost:8000 (SSH tunnel)"
echo "  Frontend: http://localhost:5173"
echo "  Press Ctrl+C to stop"
echo ""

wait
