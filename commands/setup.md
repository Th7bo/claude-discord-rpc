---
description: Configure Discord Rich Presence (set Discord Application ID, privacy options)
argument-hint: "[discord-application-id]"
---

Help the user configure the discord-rpc plugin.

Config file: `~/.config/claude-discord-rpc/config.json` (created with defaults on first hook run; create it if missing — defaults live in `DEFAULT_CONFIG` in `${CLAUDE_PLUGIN_ROOT}/claude_rpc.py`).

1. If `$ARGUMENTS` contains a numeric ID, use it as `client_id`. Otherwise, if `client_id` is empty, tell the user:
   - Open https://discord.com/developers/applications → **New Application**, name it what should appear after "Playing" (e.g. `Claude Code`).
   - Copy the **Application ID** and paste it here.
   Then wait for the ID.
2. Write `client_id` into the config, preserving other keys.
3. Ask whether project folder names and file names may be shown publicly (`show_project`, `show_file`, default true). Apply the answer.
4. Run `python3 "${CLAUDE_PLUGIN_ROOT}/claude_rpc.py" stop` then `python3 "${CLAUDE_PLUGIN_ROOT}/claude_rpc.py" test` and report the output. Discord must be running.
