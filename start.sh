#!/bin/zsh
# Starts the Hashbrown server with the API key from the Mac Keychain.
cd "$(dirname "$0")"
export HASHBROWN_API_KEY="$(security find-generic-password -a "$USER" -s hashbrown-foundry -w 2>/dev/null)"
[ -z "$HASHBROWN_API_KEY" ] && echo "⚠️ No key in the Keychain, Hashbrown will be off"
python3 server.py
