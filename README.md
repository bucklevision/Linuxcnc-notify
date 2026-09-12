# LinuxCNC Notify

Read-only remote notifications for LinuxCNC. It watches LinuxCNC's standard
Python status interface and sends alerts through any ntfy-compatible HTTPS
server. It does not consume LinuxCNC's single-consumer error queue and cannot
issue machine commands.

## Install

Download the `.deb`, then:

```bash
sudo apt install ./linuxcnc-notify_0.1.0_all.deb
sudo linuxcnc-notify pair
sudo linuxcnc-notify test
```

The installer generates a long random topic and preserves it during upgrades.
Install the ntfy app on the phone and subscribe using the server and topic shown
by `pair`. If `qrencode` is present, the command also prints a terminal QR code.

The local status and pairing page is available on the LinuxCNC computer at
<http://localhost:8765/>. It binds only to localhost by default.

## Commands

```bash
sudo linuxcnc-notify pair
sudo linuxcnc-notify test
sudo linuxcnc-notify show-config
systemctl status linuxcnc-notify
journalctl -u linuxcnc-notify -f
```

Configuration is stored at `/etc/linuxcnc-notify/config.json`. Change `server`
to use a self-hosted ntfy instance, then restart the service.

## Current event detection

- Program start (disabled by default)
- Pause
- Transition from running to stopped
- E-stop or machine power-off
- LinuxCNC connection loss during an active program
- Joint drive, hard-limit and soft-limit faults
- Execution/interpreter error states

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

## Security

The generated public-ntfy topic is a bearer secret. Do not publish it. The
configuration is mode `0600`. The web page listens on `127.0.0.1`, and the
service has no LinuxCNC command channel.

## License

GPL-2.0-or-later.
