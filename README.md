# Claude Discord RPC

Discord Rich Presence for [Claude Code](https://claude.com/claude-code). Your Discord profile shows what Claude is doing, live:

```
Playing Claude Code
Working on my-project
Editing server.py · 2 sessions
00:42 elapsed
```

- Project name, current activity (Thinking, Editing `file`, Running a command, Searching the web, Waiting for input, …) and a session timer
- Handles multiple Claude Code sessions at once and shows the most recently active one
- Python stdlib only, so there's nothing to `pip install`
- Works with regular, Flatpak, Snap and Vesktop Discord on Linux and macOS
- Clears your presence by itself when you close Claude Code

## Install

### Option A: one-liner

```bash
curl -fsSL https://raw.githubusercontent.com/Th7bo/claude-discord-rpc/main/install.sh | bash
```

The installer adds this repo as a Claude Code plugin marketplace, installs the plugin and asks for your Discord Application ID (see below). Restart Claude Code afterwards.

### Option B: inside Claude Code

```
/plugin marketplace add Th7bo/claude-discord-rpc
/plugin install discord-rpc@claude-discord-rpc
/discord-rpc:setup
```

### Option C: ask Claude

Paste this into Claude Code:

> Install https://github.com/Th7bo/claude-discord-rpc, following its README's "Instructions for Claude" section.

### Discord Application ID

Discord only shows presence for a registered application, and each user makes their own (it's free and takes 1 minute):

1. Go to <https://discord.com/developers/applications> and click **New Application**
2. Name it what should appear after "Playing", for example **Claude Code**
3. Copy the **Application ID** and give it to the installer or `/discord-rpc:setup`

You don't need to upload art: the Claude icon loads from a URL.

## Configuration

`~/.config/claude-discord-rpc/config.json`

| Key | Default | Meaning |
|---|---|---|
| `client_id` | `""` | Discord Application ID (required) |
| `show_project` | `true` | Show the project folder name. Set to `false` to show "Coding with Claude" instead |
| `show_file` | `true` | Show file names being read or edited |
| `large_image` | Claude icon URL | Image URL or asset key |
| `large_text` | `"Claude Code"` | Hover text (the model name is appended when known) |
| `button` | `null` | e.g. `{"label": "Get Claude Code", "url": "https://claude.com/claude-code"}` |
| `stale_minutes` | `45` | Drop sessions with no activity for this long |
| `idle_exit_seconds` | `60` | Daemon exits this long after the last session ends |

You can also set values from the CLI: `python3 claude_rpc.py config show_project false`.

## How it works

1. The plugin registers [hooks](https://docs.claude.com/en/docs/claude-code/hooks) for `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `Stop`, `Notification` and `SessionEnd`.
2. Each hook writes a small status file to `~/.cache/claude-discord-rpc/sessions/<session>.json` and starts the daemon if it isn't running.
3. The daemon talks to Discord over its local IPC socket. It sends a presence update only when something changed, at most once every 4 s, to stay under Discord's rate limit.
4. When no sessions are left, the daemon clears your presence and exits.

Hooks never block or fail Claude Code: errors are swallowed, and every hook has a 5 s timeout.

## Troubleshooting

```bash
P=$(ls -d ~/.claude/plugins/cache/*/discord-rpc/*/ | tail -1)   # plugin install dir
python3 "$P/claude_rpc.py" status   # config, daemon and sessions
python3 "$P/claude_rpc.py" test     # shows a test presence for 10s
python3 "$P/claude_rpc.py" stop     # stop the daemon and clear presence
cat ~/.cache/claude-discord-rpc/daemon.log
```

- **Nothing shows:** in Discord, enable *User Settings → Activity Privacy → Share your detected activities with others*.
- **`Invalid Client ID`:** the `client_id` is wrong. Copy the Application ID again, not the public key.
- **Flatpak Discord:** works by default (`$XDG_RUNTIME_DIR/app/com.discordapp.Discord/discord-ipc-0`).

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/Th7bo/claude-discord-rpc/main/uninstall.sh | bash          # keep config
curl -fsSL https://raw.githubusercontent.com/Th7bo/claude-discord-rpc/main/uninstall.sh | bash -s -- --purge
```

## Instructions for Claude

If a user asks you to install this repo, do the following:

1. Check the requirements: `python3` and the `claude` CLI are on PATH, the OS is Linux or macOS, and the Discord desktop app is installed.
2. Run `claude plugin marketplace add Th7bo/claude-discord-rpc`, then `claude plugin install discord-rpc@claude-discord-rpc`.
3. If `~/.config/claude-discord-rpc/config.json` has no `client_id`, walk the user through the **Discord Application ID** steps above and ask them to paste the ID. Don't make one up.
4. Write the ID into the config, keeping any other keys: `{"client_id": "<id>"}`.
5. Ask whether the project and file names may be shown publicly. Set `show_project` and `show_file` to match.
6. Run `python3 <plugin dir>/claude_rpc.py test` (find the dir with `ls -d ~/.claude/plugins/cache/*/discord-rpc/*/`) and report the result.
7. Tell the user to restart Claude Code so the hooks load.

Don't add the hooks to `~/.claude/settings.json` by hand: the plugin registers them. Doing both would double every update.

## License

MIT
