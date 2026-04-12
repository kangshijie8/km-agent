#!/bin/bash
set -e

# Ensure KUNMING_HOME directory exists
mkdir -p /home/kunming/.kunming

# Copy default config if it doesn't exist
if [ ! -f /home/kunming/.kunming/config.yaml ]; then
    cp /app/default-config.yaml /home/kunming/.kunming/config.yaml
fi

# Run the agent with any passed arguments
exec python -m kunming "$@"
