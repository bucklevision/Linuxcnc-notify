# Changelog

All notable changes to LinuxCNC Notify are recorded here.

## 0.3.0 - 2026-09-13

- Added one authoritative `VERSION` file.
- Added version reporting to the command line, diagnostic output, web dashboard and status API.
- Made all dashboard variable sections collapsed on first view while preserving opened sections during refreshes.
- Rewrote the installation guide for people unfamiliar with Linux administration.

## 0.2.3 - 2026-09-13

- Suppressed false E-stop-reset notifications while E-stop is being engaged.
- Published the installable Debian package in the repository.

## 0.2.2 - 2026-09-13

- Detect pause and resume using LinuxCNC's `paused`, `task_paused` and interpreter states.
- Enabled resume notifications by default for new installations.

## 0.2.1 - 2026-09-13

- Report the executing `motion_line` instead of the interpreter's read-ahead line.
- Include captured program context when power-off or E-stop interrupts a run.

## 0.2.0 - 2026-09-13

- Added selectable events in `/etc/linuxcnc-notify/notify.conf`.
- Added the live, grouped LinuxCNC status dashboard.
- Added machine power, E-stop, homing, tooling, spindle and coolant events.

## 0.1.5 - 2026-09-12

- Corrected systemd home-directory protection so the service can access LinuxCNC user data.

## 0.1.0 - 2026-09-12

- Initial Debian-package implementation with ntfy notifications, automatic topic generation and local status page.
