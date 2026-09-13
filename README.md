# LinuxCNC Notify

Read-only remote notifications for LinuxCNC. It watches LinuxCNC's standard
Python status interface and sends alerts through any ntfy-compatible HTTPS
server. It does not consume LinuxCNC's single-consumer error queue and cannot
issue machine commands.

## Installation on a LinuxCNC computer

These instructions are for a normal Debian-based LinuxCNC installation. The
package installs its required software automatically.

1. On the LinuxCNC computer, download
   [linuxcnc-notify_0.3.0_all.deb](https://github.com/bucklevision/Linuxcnc-notify/raw/refs/heads/main/dist/linuxcnc-notify_0.3.0_all.deb).
   Your browser will normally save it in the `Downloads` folder.

2. Open a terminal. On most LinuxCNC desktops, press `Ctrl` + `Alt` + `T`.

3. Enter these commands one at a time:

   ```bash
   cd ~/Downloads
   sudo apt install ./linuxcnc-notify_0.3.0_all.deb
   sudo linuxcnc-notify setup
   ```

   Enter your Linux password if requested. Nothing appears while a password is
   typed; this is normal. Press `Enter` when finished.

4. Install the **ntfy** app on the phone. Then, on the LinuxCNC computer, run:

   ```bash
   sudo linuxcnc-notify pair
   ```

   In the phone app, add a subscription using the server and topic printed by
   the command. The topic is generated uniquely for this computer. Keep it
   private because anyone who knows it can receive its messages.

5. Send a test notification:

   ```bash
   sudo linuxcnc-notify test
   ```

6. Start LinuxCNC and open <http://localhost:8765/> on the LinuxCNC computer.
   The page should show **Connected**. Its detailed sections are collapsed by
   default; click a section name to expand it.

The generated topic and notification choices are preserved when a newer
package is installed. If setup cannot identify the desktop account, use
`sudo linuxcnc-notify setup --user USERNAME`, replacing `USERNAME` with the
account used to run LinuxCNC.

## Commands

```bash
sudo linuxcnc-notify pair
sudo linuxcnc-notify test
sudo linuxcnc-notify show-config
sudo linuxcnc-notify show-notifications
sudo linuxcnc-notify doctor
linuxcnc-notify --version
systemctl status linuxcnc-notify
journalctl -u linuxcnc-notify -f
```

Server and topic configuration is stored at `/etc/linuxcnc-notify/config.json`.
Notification choices are in `/etc/linuxcnc-notify/notify.conf`. Each event accepts
`yes`, `no`, or `running` (send only while a program is active). After editing it,
restart with `sudo systemctl restart linuxcnc-notify`.

## Event detection

- LinuxCNC connected or disconnected
- Program started, paused, resumed or stopped
- Machine power on or off; E-stop engaged or reset
- Homing started or completed
- Joint drive, hard-limit and soft-limit faults
- Execution/interpreter errors
- Tool, spindle, flood coolant and mist coolant changes

LinuxCNC does not expose an unambiguous completion reason in every situation.
Version 0.1 therefore reports a clean transition as **program stopped**, rather
than claiming it completed successfully. A later optional M-code integration
can mark confirmed normal completion.

## Build

On Debian or a LinuxCNC installation:

```bash
chmod +x packaging/build-deb.sh
./packaging/build-deb.sh
```

The package is written to `dist/`.

Version history is recorded in [CHANGELOG.md](CHANGELOG.md).

## Security

The generated public-ntfy topic is a bearer secret. Do not publish it. The
configuration is mode `0600`. The web page listens on `127.0.0.1`, and the
service has no LinuxCNC command channel.

## License

GPL-2.0-or-later.

## Compatibility

The package is architecture-independent and uses only Python 3.7 standard-library
features. It targets packaged LinuxCNC 2.8 and later on Debian-derived systems,
including amd64, i386, armhf and arm64. Debian's `linuxcnc-uspace` includes the
Python interface; the alternative `python3-linuxcnc` dependency supports
distributions which split that interface into its own package. Run `doctor` to
check the three runtime requirements without starting or controlling a machine.

Run-in-place developer builds are not automatically discoverable because their
Python paths are configured by the developer shell rather than the operating
system package manager.
