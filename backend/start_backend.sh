#!/bin/bash
set -e
cd /home/gm2629/Lahn-Avatar/backend
export PATH="/home/gm2629/Lahn-Avatar/lahn_env/bin:$PATH"
export VIRTUAL_ENV="/home/gm2629/Lahn-Avatar/lahn_env"
# Disable all progress bars and interactive prompts
export TRANSFORMERS_VERBOSITY=error
export HF_HUB_DISABLE_PROGRESS_BARS=1
export HF_HUB_DISABLE_EXPERIMENTAL_WARNING=1
export TQDM_DISABLE=1
# Ensure stdout/stderr are unbuffered
exec /home/gm2629/Lahn-Avatar/lahn_env/bin/python -u server.py

