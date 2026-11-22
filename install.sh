#!/usr/bin/env bash
# Installs the discord-rpc Claude Code plugin and sets your Discord Application ID.
# Usage: curl -fsSL https://raw.githubusercontent.com/Th7bo/claude-discord-rpc/main/install.sh | bash -s -- [APPLICATION_ID]
set -euo pipefail

REPO="Th7bo/claude-discord-rpc"
MARKETPLACE="claude-discord-rpc"
PLUGIN="discord-rpc"
CONFIG="${HOME}/.config/claude-discord-rpc/config.json"

say() { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null || die "python3 is required"
command -v claude  >/dev/null || die "Claude Code CLI ('claude') not found in PATH"
case "$(uname -s)" in Linux|Darwin) ;; *) die "only Linux and macOS are supported" ;; esac

say "Adding marketplace $REPO"
claude plugin marketplace add "$REPO" || claude plugin marketplace update "$MARKETPLACE"

say "Installing plugin $PLUGIN@$MARKETPLACE"
claude plugin install "$PLUGIN@$MARKETPLACE"

CLIENT_ID="${1:-${CLAUDE_RPC_CLIENT_ID:-}}"
if [[ -z "$CLIENT_ID" && -f "$CONFIG" ]]; then
  CLIENT_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("client_id",""))' "$CONFIG" 2>/dev/null || true)"
fi
if [[ -z "$CLIENT_ID" ]]; then
  cat <<MSG

Discord needs an Application ID to show presence:
  1. Open https://discord.com/developers/applications -> New Application
  2. Name it what should appear after "Playing" (e.g. "Claude Code")
  3. Copy the Application ID

MSG
  if { true </dev/tty; } 2>/dev/null; then
    read -rp "Application ID: " CLIENT_ID </dev/tty || CLIENT_ID=""
  fi
fi

if [[ -n "$CLIENT_ID" ]]; then
  [[ "$CLIENT_ID" =~ ^[0-9]+$ ]] || die "Application ID should be numeric, got: $CLIENT_ID"
  mkdir -p "$(dirname "$CONFIG")"
  python3 - "$CONFIG" "$CLIENT_ID" <<'PY'
import json, sys
path, cid = sys.argv[1], sys.argv[2]
try:
    cfg = json.load(open(path))
except Exception:
    cfg = {}
cfg["client_id"] = cid
json.dump(cfg, open(path, "w"), indent=2)
PY
  say "Saved client_id to $CONFIG"
else
  say "No Application ID set. Run /discord-rpc:setup inside Claude Code later."
fi

say "Done. Restart Claude Code to activate the hooks."
