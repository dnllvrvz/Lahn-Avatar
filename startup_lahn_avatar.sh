#!/bin/bash

# Backend
screen -L -Logfile ~/backend-logs.0 -dmS backend bash -c 'cd ~/Lahn-Avatar && source lahn_env/bin/activate && cd backend && python server.py; exec bash'

# Frontend
screen -L -Logfile ~/frontend-logs.0 -dmS frontend bash -c 'cd ~/Lahn-Avatar/frontend && npm run dev; exec bash'

# Caddy
screen -dmS caddy bash -c 'cd ~/caddy-related && caddy run; exec bash'
