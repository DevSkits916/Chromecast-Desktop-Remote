# Chromecast Desktop Remote

A floating, resizable Windows remote for **Chromecast with Google TV**, **Google TV Streamer**, and compatible **Android TV / Google TV devices**. It sends controls directly over your local network with Android Debug Bridge (ADB). There are no accounts, cloud services, analytics, or internet-facing listeners.

> This does **not** control older cast-only Chromecast dongles. Those devices do not run the Android TV interface and do not expose the Wireless Debugging control channel used here.

## Features

- Modern dark PySide6 interface with scalable controls, hover/press feedback, compact mode, Always on Top, remembered size and position, and a minimum safe size.
- D-pad, OK, Back, Home, Power, volume, mute, play/pause, rewind, and fast-forward.
- Keyboard controls while the remote window is focused.
- In-app ADB pairing, connecting, disconnecting, readable errors, and automatic reconnect.
- Text entry into the focused TV field with spaces and common shell characters escaped.
- YouTube, Netflix, and Spotify launch buttons plus editable custom Android package buttons.
- Optional system tray behavior and Launch with Windows.
- Standalone one-file Windows build; Python is not required to run the generated EXE.

## First run

### 1. Install Android Platform Tools

ADB is intentionally not redistributed inside this repository or EXE. Google's Android SDK license restricts redistribution of SDK components. Download the current **SDK Platform-Tools for Windows** from the [official Android page](https://developer.android.com/tools/releases/platform-tools), accept Google's terms, unzip it, and keep the complete `platform-tools` folder together (including its DLLs).

The remote automatically looks in your PATH, Android Studio's standard SDK folder, and `C:\Android\platform-tools`. Otherwise, open **Settings → Path to adb.exe → Browse** and choose `platform-tools\adb.exe`. A missing ADB installation shows a setup message and never crashes the app.

### 2. Enable developer options on the TV

Menu names vary slightly by Google TV version:

1. Open **Settings → System → About**.
2. Select **Android TV OS build** seven times until developer mode is enabled.
3. Open **Settings → System → Developer options**.
4. Turn on **Wireless debugging**. Keep the PC and TV on the same trusted local network.

### 3. Pair once

1. On the TV's **Wireless debugging** screen, choose **Pair device with pairing code**.
2. In the desktop remote choose **Pair device**.
3. Enter the TV IP, the temporary pairing port, and the displayed pairing code.
4. Click **Pair**. Pairing authorization normally persists until it is revoked on the TV.

### 4. Connect

The Wireless Debugging screen also shows an **IP address & port** for normal connections. That connection port can differ from both the temporary pairing port and the traditional `5555` default.

1. Enter the TV IP and its current connection port in the remote.
2. Click **Connect**.
3. Leave **Auto-connect on startup** enabled in Settings if the address is stable.

If the TV changes the connection port after a restart, copy the new port from its Wireless Debugging screen. Reserving the TV's IP in the router can make reconnection more predictable.

## Keyboard shortcuts

| Windows key | TV action |
|---|---|
| Arrow keys | D-pad |
| Enter | OK / Select |
| Escape or Backspace | Back |
| H | Home |
| Space | Play / Pause |
| Page Up | Volume Up |
| Page Down | Volume Down |

Shortcuts are paused while typing in an IP, port, pairing-code, or text-entry field so normal editing remains possible.

## Android key events

| Control | Android key code |
|---|---:|
| Up / Down / Left / Right | 19 / 20 / 21 / 22 |
| OK | 23 (`DPAD_CENTER`) |
| Back / Home / Power | 4 / 3 / 26 |
| Volume Up / Down / Mute | 24 / 25 / 164 |
| Play-Pause / Rewind / Fast Forward | 85 / 89 / 90 |

## App buttons

The default package identifiers were checked against the Google Play listings for the TV apps:

- YouTube for Android TV: `com.google.android.youtube.tv`
- Netflix: `com.netflix.ninja`
- Spotify for TV: `com.spotify.tv.android`

TV manufacturers and regional variants can ship different identifiers. Open **Settings → Apps** to add or remove buttons without changing code. The launcher uses Android's package launcher rather than relying on an internal activity name.

## Run from source

Windows PowerShell:

```powershell
cd "$HOME\Documents\Chromecast-Desktop-Remote"
.\run.ps1
```

Or set up manually:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## Build the standalone EXE

```powershell
cd "$HOME\Documents\Chromecast-Desktop-Remote"
.\build.ps1 -Clean
```

The build script creates a local virtual environment, installs pinned-compatible dependencies, generates the Windows icon, embeds version metadata, and writes:

```text
release\ChromecastRemote.exe
```

The EXE does not need Python, but ADB remains an external prerequisite for licensing and updateability. Keep `adb.exe` with the other files from Google's Platform Tools download.

The packaging step temporarily isolates its DLL search path and excludes Qt's unused networking bindings. This prevents unrelated OpenSSL DLLs installed by other Windows applications from being accidentally bundled with Qt.

## Settings and privacy

Settings are stored per user at:

```text
%LOCALAPPDATA%\ChromecastDesktopRemote\settings.json
```

The app stores the selected ADB path, TV address/port, window geometry, preferences, and custom app buttons. It stores no TV pairing code, password, cookie, account, or media history. Communication is initiated locally by ADB to the address you enter.

## Troubleshooting

- **ADB was not found:** Choose the exact `adb.exe` in Settings. Do not copy only the EXE out of Platform Tools; its neighboring DLLs may be required.
- **Could not reach the TV:** Confirm both devices are on the same LAN, Wireless debugging is enabled, and use the current connection port shown by the TV—not the temporary pairing port.
- **Unauthorized:** Pair again and accept any authorization prompt on the TV. If needed, forget the computer under Paired devices and repeat pairing.
- **Offline:** Wake the TV, reopen Wireless debugging, then Disconnect and Connect.
- **Port changed:** Update the port shown on the TV. Google TV can rotate its wireless ADB port.
- **Power does not wake a sleeping TV:** Network ADB may stop while the TV is deeply asleep. Wake it with the physical remote, HDMI-CEC, or another supported method, then reconnect.
- **Text characters differ:** Android's `input text` is best for ordinary Latin text. TV keyboard/IME implementations may handle punctuation or non-Latin characters differently.
- **App does not launch:** Confirm the app is installed and edit its package name in Settings. Package variants can differ by device, vendor, or region.
- **Multiple ADB devices:** Every remote command includes the configured TV serial (`IP:port`), so another USB or network device should not receive the key.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
```

Automated tests cover configuration persistence, corrupt-config recovery, text escaping, friendly ADB failures, missing ADB behavior, window construction, and compact/full modes. A real Google TV is still required to validate device authorization, vendor-specific power behavior, all key responses, installed app variants, and the TV's current input-method behavior.

## Project structure

```text
app.py                         Entry point
chromecast_remote/             UI, ADB layer, settings, styles
assets/                        Source icon
tests/                         Unit and offscreen UI tests
build.ps1                      Standalone Windows build
run.ps1                        First-run source launcher
requirements*.txt              Runtime and test dependencies
version_info.txt               Windows EXE metadata
```
