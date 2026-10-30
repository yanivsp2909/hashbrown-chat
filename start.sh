#!/bin/zsh
# Starts the Hashbrown server with the API key from the Mac Keychain.
cd "$(dirname "$0")"
export HASHBROWN_API_KEY="$(security find-generic-password -a "$USER" -s hashbrown-foundry -w 2>/dev/null)"
[ -z "$HASHBROWN_API_KEY" ] && echo "⚠️ No key in the Keychain, Hashbrown will be off"
# The /admin password, from the Keychain item "hashbrown-admin" (never in the code: the repo is public)
export HASHBROWN_ADMIN_PASSWORD="$(security find-generic-password -a "$USER" -s hashbrown-admin -w 2>/dev/null)"
[ -z "$HASHBROWN_ADMIN_PASSWORD" ] && echo "⚠️ No admin password in the Keychain, /admin will be off"
# Use the project's .venv if it exists, because that's where the openai package is installed
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
"$PY" server.py
