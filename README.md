# Chromecast Desktop Remote — v1.3.0

A local Windows remote for Chromecast with Google TV, Google TV Streamer, and compatible Android TV / Google TV devices that expose ADB. The normal screen stays focused on D-pad, OK, Back, Home, Power, Volume and Mute. Media, text, installed apps, APK installation and diagnostic information live behind **Advanced**.

Older cast-only Chromecast dongles are unsupported: they do not run Android TV or expose this ADB control channel. Wireless pairing availability varies by Android version and vendor. Consult [Google's ADB guide](https://developer.android.com/tools/adb) if your TV does not expose Wireless debugging.

## First-time setup

1. Run the EXE or use the source instructions below. Help opens until setup succeeds, when ADB is missing, or when no TV is configured. Reopen it with **Help** at any time. **Settings → General → Show setup help at startup** overrides this behavior.
2. Open **Connection setup → Set up ADB**, read Google's SDK terms, accept them, and download official Windows Platform Tools. You can instead select your existing `adb.exe` in **Settings → ADB**.
3. On the TV, open **Settings → System → About** and click **Android TV OS build** seven times. Enable **Developer options → Wireless debugging**. Keep the TV and PC on the same trusted LAN. Menu names vary by vendor.
4. On the TV choose **Pair device with pairing code**. In the remote choose **Pair device**, enter its IP, choose **Detect pairing port**, and enter the code. The pairing port is temporary and differs from the connection port. The code is masked, cleared after submission and never saved.
5. Use **Connect** or **Auto Detect**. Choose the intended TV when multiple unknown devices are advertised. Manual IP and connection-port entry remains available when the network blocks mDNS.

ADB authorization remains controlled by Android. This application cannot bypass pairing, signature checks, device policy, or installation restrictions.

## Device profiles and discovery

Use the TV selector to switch devices. **Add**, **Rename**, and **Remove** manage friendly names; Add accepts an IP or leaves it blank for discovery. **Settings → Devices** edits the selected TV's address, port and auto-connect preference. Each profile stores the discovered service identity, manufacturer/model, Android version/API level, last connected time and favorite packages.

Discovery deduplicates repeated endpoints, keeps pairing services separate, and matches the saved service identity before falling back to its IP. A saved TV that disappears never causes a different advertised TV to be selected. An IP reassigned to a different device cannot be reliably distinguished without a stable mDNS identity; confirm the selected TV when using manual addresses. A named profile with no address can be populated through discovery.

Connected TVs receive a lightweight `get-state` heartbeat every 15 seconds. Failures trigger discovery and reconnection using 5, 10, 20, 40 and then 60 second delays. A newly advertised port is saved. Authorization errors require pairing again. **Disconnect** pauses recovery until you explicitly connect again. Deeply sleeping TVs may need the physical remote to wake up.

Connection states distinguish missing ADB, searching, found, pairing, connecting, connected, offline, unauthorized and reconnecting. An ADB connect response is followed by a targeted state check before setup is marked complete. Duplicate discovery and connect jobs are suppressed. Results from an earlier profile generation are discarded.

## Remote and compact mode

Hold D-pad directions, Volume Up/Down, Rewind or Fast Forward: one command is sent immediately, followed by a 350 ms delay and 110 ms repeats. Release, hiding a control or disabling it cancels its timers. The command queue is bounded so a slow TV does not accumulate an unbounded backlog; actual repeat speed depends on ADB latency.

**Compact** hides the profile selector, connection setup and all Advanced sections. Essential controls and connection status remain visible. The preference, window geometry, always-on-top, Windows startup and tray settings are remembered. Settings and Help remain reachable in compact mode. The window is resizable and D-pad controls expand with available space.

**Advanced → Media** offers Play/Pause, Rewind, Fast Forward, Previous, Next and Stop. App support for individual media keycodes varies.

## Keyboard shortcuts

| Key | TV action |
|---|---|
| Arrows | D-pad |
| Enter | OK |
| Escape / Backspace | Back |
| H | Home |
| Page Up / Page Down | Volume Up / Down |
| Space | Play / Pause |
| M | Mute |
| R / F | Rewind / Fast Forward |
| P / N | Previous / Next |

Shortcuts apply while the remote is active and pause in editable controls and modal dialogs. Keyboard auto-repeat is suppressed; hold-to-repeat is available through the remote buttons. Global Windows hotkeys are intentionally deferred; the app registers none.

## Text entry

Focus the desired input on the TV, then use **Advanced → Text → Send Text**. Shell metacharacters are escaped, line breaks/tabs become spaces, and NUL characters are rejected. Android `input text` has limitations with non-Latin characters, literal `%s` and vendor keyboards. It is not a full Unicode clipboard bridge.

## Installed apps and favorites

Connect and open **Advanced → Apps → Refresh**. The remote queries installed package names and system packages in the background, caches results per device for the current session, and supports search, Launch, Favorite and Info. Favorites are saved per profile and sorted first. Labels are package names, not translated application titles. Launch uses Android's launcher category; packages without a launcher may not open. There are no hardcoded Netflix/YouTube/Spotify dependencies.

**Info** displays package details in the Device / ADB tab. **Uninstall** requires an explicit confirmation that local app data may be erased. System packages and packages whose system classification has not been loaded cannot be removed through this interface. Device restrictions are respected. Refresh updates the list; a successful uninstall triggers refresh automatically.

## APK sideloading

Use **Advanced → APK → Browse**, or drop a single local `.apk` on the window, then click **Install**. Installation requires a connection, shows the filename, validates the ZIP/manifest and size, and invokes `adb -s IP:PORT install -r` in a worker. Duplicate installs are prevented. Status reports preparation, installation and the actual final result; it does not invent percentages or transfer milestones that ADB does not expose.

The file-size limit is 2 GB. APK compatibility and signatures are ultimately validated by Android. Only install trusted APKs. Replacement updates normally preserve data when Android accepts the package.

### Split-package limitation

`.apks`, `.xapk` and `.apkm` containers are deliberately rejected. Blindly installing every enclosed APK is unreliable: archives can contain mutually exclusive CPU/density/language variants, multiple base packages or expansion assets. Device-aware `.apks` selection uses [Google's bundletool](https://developer.android.com/tools/bundletool), which adds a separate Java/tooling runtime; third-party formats have additional metadata differences. This release preserves safe single-APK installation rather than guessing the correct split set. No archive paths from those containers are extracted. Obtain a compatible universal APK or install using the format publisher's trusted tools.

## Device and ADB information

**Advanced → Device / ADB** displays the saved name, manufacturer, model, Android version/API level, IP, port, connection state and selected ADB path. Missing getprop fields show **Unavailable**. Use **Refresh Device Info** and **ADB version** for live details.

The managed installer reads `source.properties` for its installed Platform Tools revision and records the downloaded archive's SHA-256 for diagnostics. That recorded hash is **not** an independently verified upstream checksum. No unverifiable SHA-256 is hardcoded. Downloads use Google's official HTTPS host, bounded download/expanded sizes, required-file validation and extraction of only expected filenames. Replacement stages the new runtime and retains the old directory until the replacement succeeds. A running ADB executable may prevent replacement on Windows; close other ADB clients and retry.

**Check Platform Tools update** queries Google's official repository metadata and displays its newest revision; compare it with the installed revision. **Repair / reinstall managed ADB** explicitly downloads the current package again. A manually selected external ADB remains selected after managed installation and is never replaced. Select `%LOCALAPPDATA%\ChromecastDesktopRemote\platform-tools\adb.exe` in Settings to switch to managed ADB.

## Application updates

**Settings → Updates** or **Advanced → Device / ADB** can check the latest GitHub release for `DevSkits916/Chromecast-Desktop-Remote`. Stable semantic versions are compared with v1.3.0. Offline, malformed and unavailable responses fail gracefully. **View Release** opens the official release page. Checks run only when clicked; the remote does not automatically download or execute release binaries.

## Settings, migration and privacy

Configuration lives at:

```text
%LOCALAPPDATA%\ChromecastDesktopRemote\settings.json
```

Schema version 2 automatically migrates the old single-TV address, connection port and auto-connect preference into **My TV**. ADB selection, compact/top/startup/tray preferences and geometry are retained. Legacy address keys remain compatibility mirrors for the selected profile. Migration is idempotent. Settings are saved through temporary-file replacement. Malformed JSON or wrong types recover to safe defaults; unknown settings are ignored. Back up this file before downgrading, because older versions do not understand profiles.

Settings categories are General, Devices, Remote, Keyboard, ADB and Updates. Favorites, service identity and recent connection time are stored locally. No telemetry, cloud account or pairing code is stored. Control commands stay on the LAN. Internet access occurs only for explicit Google downloads/version checks or GitHub release checks. No additional public network listener is introduced.

## Run from source

Windows PowerShell:

```powershell
cd "$HOME\Documents\Chromecast-Desktop-Remote"
.\run.ps1
```

Manual setup:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

For Linux/WSL source testing, install an appropriate Qt display environment and external `adb`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

The managed installer and startup shortcut target Windows; Linux GUI operation and WSL network discovery are not release-validated.

## Build a standalone Windows EXE

```powershell
.\build.ps1 -Clean
```

Output: `release\ChromecastRemote.exe`. Python is not required on the destination PC. Google binaries are downloaded after terms acceptance and are not bundled in the EXE or repository. Build output, caches, settings and generated icons remain ignored. The existing PySide6-Essentials / PyInstaller flow isolates its DLL search path and excludes unused Qt networking modules to avoid unrelated OpenSSL conflicts.

## Tests and physical-device validation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
```

Normal tests require no TV and isolate local settings and startup jobs. They cover old configuration migration, malformed configuration, profile selection, stale generations, duplicate/malformed discovery, changed ports, disappearance, recovery backoff, explicit disconnect, state transitions, getprop parsing, media keycodes, text escaping, package validation, long-press timing, APK/container validation, update failure handling and UI/compact/settings construction.

Physical Google TV testing is still required for pairing/authorization, real mDNS advertisements and port changes, actual heartbeat/reconnect behavior after sleep, hold responsiveness, volume/power/media support, text/IME compatibility, package launch/uninstall and real APK installation. Mocked tests and an EXE launch do not prove those device behaviors.

## Troubleshooting

- **ADB missing:** use Set up ADB or select an existing executable in Settings.
- **No service discovered:** enable Wireless debugging, keep both devices on the same non-guest network, or enter the current connection port manually. Pairing and connection ports differ.
- **Wrong saved IP:** update the selected profile. A saved profile is not replaced with another TV just because another service is visible.
- **Unauthorized:** pair again, accept TV prompts, or revoke the old authorization on the TV and repeat pairing.
- **Offline / sleeping:** wake the TV using its physical remote. Explicit Disconnect pauses automatic recovery; Connect resumes it.
- **Install blocked:** inspect the TV's approval prompt, storage and device policy. The app does not bypass restrictions.
- **Signature mismatch / downgrade:** obtain a compatible APK. Uninstalling the existing copy may erase local data.
- **App does not launch:** not every installed package contains a launcher activity. Vendor launch behavior varies.
- **Managed repair fails:** close ADB clients and retry. External ADB selection is retained.
- **Release check fails:** verify internet access or open the GitHub release page manually.

## Project structure

```text
app.py                         Entry point
chromecast_remote/app.py       Qt application startup/metadata
chromecast_remote/ui.py        Remote, dialogs, advanced panels, hold timers
chromecast_remote/adb.py       Targeted async commands and safe parsers
chromecast_remote/connection.py Connection state/backoff and profile matching
chromecast_remote/config.py    Schema migration, persistence and startup
chromecast_remote/platform_tools.py Managed official ADB installation
chromecast_remote/updates.py    Explicit GitHub/Google version checks
chromecast_remote/styles.py    Dark interface styling
assets/icon.svg                Source icon
tests/                         Unit and offscreen Qt tests
build.ps1 / run.ps1             Windows packaging and source launcher
requirements*.txt              Runtime/build and test dependencies
version_info.txt               Windows EXE metadata
```
