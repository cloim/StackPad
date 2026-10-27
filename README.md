# StackPad

[한국어](README.ko.md)

StackPad turns the servers on your Windows PC into a pad of buttons. Tap a pad to start a dev server, a group of services, a Docker container or a systemd service on a remote Linux box, and tap again to stop it. Check logs, health and AI CLI usage from the PC or from your phone.

- 16 pads per pad set, as many pad sets as you like
- Local commands, Docker containers and remote servers over SSH, alone or grouped into one pad with ordered start and reverse stop
- Scenes to chain multiple pads in sequence, and schedules to trigger pads or scenes automatically by time and day
- Automatic crash restart with backoff, error line detection, and instant failure alerts (PC toast and Android persistent foreground notifications)
- Real-time SSE push updates, incremental log streaming, and log search with error line filtering
- Breathing LED ring, 60-slot LCD dot-matrix sparklines for CPU and memory
- Suggestions for servers already running under your project folder
- Sign in with your Google account; reach the PC from your phone through Tailscale
- Android app with a home screen widget for Claude Code, Codex and Antigravity usage limits
- English and Korean

## Requirements

- Windows 10 or 11 (64-bit). The installer adds Microsoft Edge WebView2 when it is missing.
- A Google account and a Google OAuth client you create yourself (free, about 5 minutes, see below)
- Optional: [Tailscale](https://tailscale.com/download) on the PC and your phone, for remote access
- Optional: Docker Desktop, VS Code and OpenSSH for the matching features

## Install

Download from [Releases](https://github.com/cloim/StackPad/releases/latest):

| File | Use |
|---|---|
| `StackPad_x.y.z_x64-setup.exe` | Installer. Updates itself from the tray menu. |
| `StackPad-Windows-x64-portable.zip` | Unzip and run `StackPad.exe`. Keep `StackPadEngine.exe` beside it. The tray links to new versions. |
| `StackPad.apk` | Android app (Android 8 or later) |

StackPad is not code-signed. Windows SmartScreen may say "Windows protected your PC"; choose **More info > Run anyway**. Some antivirus products flag unsigned apps that start background processes; allow StackPad if that happens.

## First run

StackPad runs a small engine on `http://127.0.0.1:48731` that keeps your services running even when the window is closed. The first start walks you through:

1. **Remote access (optional).** If Tailscale is installed and signed in, **Connect** creates an HTTPS address such as `https://my-pc.tailnet-name.ts.net` that only your Tailscale devices can open. Your other `tailscale serve` entries are left untouched.
2. **Google sign-in.** Create an OAuth client:
   1. Open [Google Cloud Console > Google Auth Platform > Clients](https://console.cloud.google.com/auth/clients) and pick or create a project.
   2. If asked to configure the Auth Platform, choose **External** as the audience. In **Audience > Test users**, add every Google account that will sign in. That is all StackPad needs; Google does not review apps that only ask for an email address.
      To publish the client instead (no test user list), Branding needs a home page and a privacy policy link; you can use `https://cloim.github.io/StackPad/` and `https://cloim.github.io/StackPad/privacy.html`.
   3. **Create client**, type **Web application**. Add every redirect URI that StackPad shows, for example `http://127.0.0.1:48731/api/auth/google/callback` and `https://my-pc.tailnet-name.ts.net/api/auth/google/callback`.
   4. Paste the client ID and client secret into StackPad.
3. **Sign in on the PC.** The first Google account that signs in on the PC becomes the owner. Add other accounts in **Settings > Account**.
4. **Project folder.** Tell StackPad where your projects live. It becomes the default working folder and the folder that registration suggestions scan.

Settings, logs and sign-in records are stored in `%USERPROFILE%\.config\stackpad`. Secrets are never sent anywhere except Google during sign-in, and sign-in sessions are stored only as hashes.

## Everyday use

- Tap an empty pad (or **+**) to add a service: a command and working folder, a Docker container, or a remote server with start, stop and status commands. Add more services to make a group pad.
- Configure auto-restart policies (`on-failure` with exponential backoff up to a maximum retry limit) and toast/push notifications for crash alerts.
- Group multiple pads into **Scenes** to start them in sequence and stop them in reverse order.
- Schedule automatic pad or scene starts and stops by local time and day of the week under **Scenes > Schedules**.
- Tap a pad to start it, tap again to stop. The pad menu has details and logs, settings, open in browser and open in VS Code.
- Search service logs in real time, toggle the "Errors only" filter, and jump directly to crash error lines.
- Enjoy dynamic breathing LED rings matching CPU activity, 60-slot dot-matrix LCD sparklines for CPU and memory history.
- Drag pads to rearrange them; on touch screens use the handle at the top left.
- A server you started outside StackPad shows as **Running outside**; tap it to let StackPad take it over.
- **Settings > General**: language, start with Windows, log retention, AI usage, and the storage folder.
- Tray menu: open, close the window (engine and services keep running), quit StackPad (optionally stopping every service), and install updates.

## Command line

`stackpad-cli`, installed beside `StackPad.exe`, lets scripts and AI coding agents manage pads without the screen. The installer adds the StackPad folder to your user PATH; open a new terminal after installing. `StackPad.exe` takes the same commands, but as a windowed app it is waited for only when its output is piped (Bash, Python), so use `stackpad-cli` in PowerShell and cmd.

```powershell
stackpad-cli help                     # every command; help pad lists the pad options and colors
stackpad-cli padset list              # pad sets with their free slots
stackpad-cli padset add Work
stackpad-cli pad add --name API --command "uv run main.py" --cwd D:\app --port 8000 --padset Work --restart on-failure
stackpad-cli pad list --padset Work
stackpad-cli pad start API
stackpad-cli pad logs API
stackpad-cli pad update API --environment production  # Set the DEV/PRD environment
stackpad-cli pad show API             # its "input" can be edited and passed back with pad update API --json -
stackpad-cli scene add --name DevStack --pads API,Web
stackpad-cli scene start DevStack
stackpad-cli schedule add --scene DevStack --action start --time 09:00 --days mon-fri
```

- Pads, scenes, and pad sets are named by ID or by name. Slots are 0 to 15, row by row from the top left.
- Results are JSON on standard output, errors go to standard error. Exit codes: 0 success, 1 failed, 2 wrong command, 3 engine not running.
- Group pads and remote server pads are written as JSON with `--json FILE` or `--json -` (standard input).
- New pads without an explicit color use the least-used palette color across all pad sets at creation time. Each group counts as one pad; ties follow palette order. `--color` and JSON colors take priority, and updates keep the existing color.
- Commands talk to the running engine with the token it keeps in `%USERPROFILE%\.config\stackpad`, so they work only on this PC, for this Windows user, while StackPad is running (`StackPad.exe --hidden` starts it without the window).

## Phone

- **Android:** install `StackPad.apk`, turn on Tailscale on the phone, then on the PC open **Settings > Account > Connect a phone** and scan the QR code with the app. The code works once for five minutes. Once connected, the app opens the screen from your PC, so PC updates reach the phone without reinstalling the app. Connected phones are listed there and can be disconnected. Long-press the home screen to add the **Agent limits** widget.
  - The Android app includes a persistent Foreground Service that keeps an SSE connection with the engine to deliver immediate failure and crash alert notifications even when the app is in the background. For uninterrupted notifications, disable battery optimization and allow background autostart for StackPad in your device settings.
- **iPhone and others:** open the Tailscale address in Safari or Chrome, sign in with Google and add it to the home screen.

## AI usage (optional)

StackPad can show the 5-hour and weekly limits of the AI CLIs signed in on the PC: Claude Code, Codex and Antigravity. It is off by default; turn on each CLI in **Settings > General**. StackPad only reads the credentials those CLIs already saved and calls their unofficial usage endpoints, so the numbers may disappear if those services change.

## Remote servers

Remote pads run your commands over SSH with your own keys (`~/.ssh/config` aliases work). Nothing is installed on the server. Connect once from a terminal to save the host key, and allow commands that need `sudo` without a password in the server's sudoers file. Remote pads can only be added or changed from the PC itself.

## Security notes

- The engine listens on `127.0.0.1` only. Remote access goes through Tailscale, so only your tailnet devices can reach it, and every request still needs an allowed Google account.
- Commands run as your Windows user. Only add Google accounts you trust with that.
- The OAuth client secret is stored in the local settings file.
- The command line needs no Google sign-in: it uses the engine token readable only by your Windows user, and the engine accepts it only from this PC.

## Development

```powershell
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
npm install
npm run dev                         # web screen with hot reload, proxies /api to the engine
.venv\Scripts\python backend\main.py --data-dir .test-data --port 48731
.venv\Scripts\python -m unittest discover tests
node scripts/i18n-check.mjs         # every UI message has an English translation
python scripts/build.py             # portable build in release/StackPad
python scripts/build-android.py     # Android APK, needs ANDROID_HOME and JAVA_HOME
```

Messages are written in Korean in the source and translated through `src/locales/en.js` (screen) and `backend/i18n.py` (engine).

After changing pad schedules or flow editing, run `npm run build` followed by `node scripts/pad-automation-ui-test.mjs` from the project root before delivering the change. The test requires the installed Playwright Chromium browser and uses a mock API without starting a server or changing engine data. Exit code 0 confirms draft saving, cancellation, retries, flow management, and mobile layout; failures save `.jobs/pad-automation-fail.png`. Inspect the failure, fix it, and rerun before delivery.

Pushing a tag such as `v1.2.0` builds the installer, the portable zip, the updater files and the signed APK on GitHub Actions and publishes them to Releases. Keep the version in `package.json`, `src-tauri/Cargo.toml` and `backend/main.py` in step; `tests/test_version.py` checks them.

## License

[MIT](LICENSE)
