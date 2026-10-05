#!/usr/bin/env bash
set -e

echo "============================================================"
echo " Starting Nagpur Estates AI Voice CRM & Production Services "
echo "============================================================"

# Detect dynamic PORT from cloud provider (Hugging Face: 7860, Render: 10000, default: 7860)
PORT="${PORT:-7860}"
HOST="${API_HOST:-0.0.0.0}"

export API_PORT="$PORT"
export API_HOST="$HOST"

echo "Binding HTTP Server to ${HOST}:${PORT}..."

# Check if LiveKit credentials exist to determine if agent worker should run in parallel
if [ "${RUN_AGENT_IN_BACKGROUND:-true}" = "true" ] && [ -n "$LIVEKIT_URL" ] && [ -n "$LIVEKIT_API_KEY" ]; then
    echo ">> LiveKit configuration detected. Launching Gemini Live Native Agent worker in background..."
    python -u agent.py start &
    AGENT_PID=$!
    echo ">> Agent Worker running with PID: $AGENT_PID"
fi

# Launch FastAPI web application server
exec python -u main.py
