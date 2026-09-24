<img width="403" height="587" alt="Screenshot 2026-09-22 072116" src="https://github.com/user-attachments/assets/cad7d10f-65b9-489b-96f1-e86dfbac94d5" />
# Chromecast Desktop Remote

A floating, resizable Windows remote for **Chromecast with Google TV**, **Google TV Streamer**, and compatible **Android TV / Google TV devices**. It sends controls directly over your local network with Android Debug Bridge (ADB). There are no accounts, cloud services, analytics, or internet-facing listeners.

> This does **not** control older cast-only Chromecast dongles. Those devices do not run the Android TV interface and do not expose the Wireless Debugging control channel used here.

## Features

- Modern dark PySide6 interface with scalable controls, hover/press feedback, compact mode, an optional Always on Top setting, remembered size and position, and a minimum safe size.
- D-pad, OK, Back, Home, Power, volume, and mute.
- Keyboard controls while the remote window is focused.
- In-app managed ADB setup, pairing, mDNS port detection, connecting, readable errors, and automatic reconnect.
- APK sideloading with a native file picker, safe per-device targeting, update-in-place support, and readable install errors.
- Optional system tray behavior and Launch with Windows.
- Standalone one-file Windows build; Python is not required to run the generated EXE.

## First run

### 1. Set up managed ADB

ADB is not redistributed inside this repository or EXE. On first run, choose **Set up ADB**, read and accept Google's Android SDK terms, then choose **Download and install**. The app downloads the current official Windows Platform Tools directly from `dl.google.com`, validates the archive structure, and installs the required ADB runtime in your local AppData folder.

No terminal, manual extraction, system-wide installation, or separate ADB download is required. An existing ADB installation can still be selected in Settings as an optional fallback.

### 2. Enable developer options on the TV

Menu names vary slightly by Google TV version:

1. Open **Settings → System → About**.
2. Select **Android TV OS build** seven times until developer mode is enabled.
3. Open **Settings → System → Developer options**.
4. Turn on **Wireless debugging**. Keep the PC and TV on the same trusted local network.

### 3. Pair once

1. On the TV's **Wireless debugging** screen, choose **Pair device with pairing code**.
2. In the desktop remote choose **Pair device**.
3. Choose **Detect pairing port** or enter the TV IP and temporary pairing port manually, then enter the displayed pairing code.
4. Click **Pair**. Pairing authorization normally persists until it is revoked on the TV.

### 4. Connect

The normal connection port can differ from both the temporary pairing port and the traditional `5555` default. The remote discovers the current `_adb-tls-connect._tcp` service over the local network, so port changes do not normally require manual entry.

1. Turn on **Wireless debugging** on the TV.
2. Click **Auto-detect port**, or simply click **Connect** with automatic port detection enabled.
3. If more than one TV is found, choose the intended device.
4. Leave **Auto-connect on startup** enabled to detect and reconnect on future launches.

Manual IP and port fields remain available as a fallback for networks that block mDNS discovery.

## Keyboard shortcuts

| Windows key | TV action |
|---|---|
| Arrow keys | D-pad |
| Enter | OK / Select |
| Escape or Backspace | Back |
| H | Home |
| Page Up | Volume Up |
| Page Down | Volume Down |

Shortcuts are paused while typing in an IP, port, or pairing-code field so normal editing remains possible.

## Android key events

| Control | Android key code |
|---|---:|
| Up / Down / Left / Right | 19 / 20 / 21 / 22 |
| OK | 23 (`DPAD_CENTER`) |
| Back / Home / Power | 4 / 3 / 26 |
| Volume Up / Down / Mute | 24 / 25 / 164 |

## Sideload an APK

1. Connect the remote to the TV.
2. In full mode, find **Sideload APK** and choose **Browse**.
3. Select one local `.apk` file and click **Install**.
4. Keep the TV awake while the status message shows that installation is in progress.

The app runs `adb -s TV_IP:PORT install -r selected.apk` in the background. The `-r` option updates an already installed app while preserving its data when Android considers the APK compatible. APK paths containing spaces are passed safely without invoking a command shell.

Only install APKs from sources you trust. The remote does not bypass Android signature checks, device policies, architecture requirements, minimum Android versions, or user-confirmation prompts. Split APK bundles such as `.apks`, `.xapk`, and `.apkm` are not single APK files and are not supported by this button.

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

The EXE does not need Python or a preinstalled copy of ADB. The user accepts Google's terms in-app and the remote downloads Platform Tools directly from Google on first run; the Google binaries are not redistributed inside this release.

The packaging step temporarily isolates its DLL search path and excludes Qt's unused networking bindings. This prevents unrelated OpenSSL DLLs installed by other Windows applications from being accidentally bundled with Qt.

## Settings and privacy

Settings are stored per user at:

```text
%LOCALAPPDATA%\ChromecastDesktopRemote\settings.json
```

The app stores the managed ADB path, terms-acceptance preference, TV address/port, window geometry, and preferences. It stores no TV pairing code, password, cookie, account, or usage history. Internet access is used only when you explicitly download Platform Tools from Google; TV control remains local.

## Troubleshooting

- **ADB is not ready:** Choose **Set up ADB**, accept Google's terms, and let the remote download the official runtime. Settings can still select an existing `adb.exe` if preferred.
- **Could not reach the TV:** Confirm both devices are on the same LAN, Wireless debugging is enabled, and use the current connection port shown by the TV—not the temporary pairing port.
- **Unauthorized:** Pair again and accept any authorization prompt on the TV. If needed, forget the computer under Paired devices and repeat pairing.
- **Offline:** Wake the TV, reopen Wireless debugging, then Disconnect and Connect.
- **Port was not detected:** Confirm Wireless debugging is on and both devices are on the same non-guest LAN. Some routers block mDNS between wireless clients; enter the port shown by the TV as a fallback.
- **Power does not wake a sleeping TV:** Network ADB may stop while the TV is deeply asleep. Wake it with the physical remote, HDMI-CEC, or another supported method, then reconnect.
- **Text characters differ:** Android's `input text` is best for ordinary Latin text. TV keyboard/IME implementations may handle punctuation or non-Latin characters differently.
- **App does not launch:** Confirm the app is installed and edit its package name in Settings. Package variants can differ by device, vendor, or region.
- **APK installation is blocked:** Keep the TV awake and check for an approval prompt. Device policy or app verification can refuse sideloading even while ADB remote commands work.
- **Version downgrade:** Install a newer APK, or uninstall the newer TV app first. Uninstalling can erase its local data.
- **Incompatible update/signature:** The installed copy and selected APK were signed differently. Use an APK from the same publisher/signing source or uninstall the existing app first.
- **Invalid APK:** Confirm it is a single `.apk` built for the TV's Android version and CPU architecture. Split-package bundles are not supported.
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
