#!/usr/bin/env bash
# Removes the discord-rpc plugin, stops the presence daemon, and deletes its state.
set -uo pipefail
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/claude-discord-rpc"

if [[ -f "$CACHE/daemon.pid" ]]; then
  kill "$(cat "$CACHE/daemon.pid")" 2>/dev/null && echo "stopped presence daemon"
fi
claude plugin uninstall discord-rpc@claude-discord-rpc 2>/dev/null || claude plugin uninstall discord-rpc 2>/dev/null || true
claude plugin marketplace remove claude-discord-rpc 2>/dev/null || true
rm -rf "$CACHE"
if [[ "${1:-}" == "--purge" ]]; then
  rm -rf "$HOME/.config/claude-discord-rpc" && echo "removed config"
else
  echo "config kept at ~/.config/claude-discord-rpc (pass --purge to delete)"
fi
echo "Uninstalled. Restart Claude Code."
