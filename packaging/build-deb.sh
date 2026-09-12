#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=${VERSION:-0.1.5}
BUILD="$ROOT/build/linuxcnc-notify_${VERSION}_all"
OUT="$ROOT/dist"
rm -rf "$BUILD"
mkdir -p "$BUILD/DEBIAN" "$BUILD/usr/bin" "$BUILD/usr/lib/python3/dist-packages" \
    "$BUILD/lib/systemd/system" "$OUT"
cp "$ROOT/packaging/control" "$BUILD/DEBIAN/control"
sed -i "s/^Version:.*/Version: $VERSION/" "$BUILD/DEBIAN/control"
cp "$ROOT/packaging/postinst" "$ROOT/packaging/prerm" "$BUILD/DEBIAN/"
chmod 755 "$BUILD/DEBIAN/postinst" "$BUILD/DEBIAN/prerm"
cp -a "$ROOT/src/linuxcnc_notify" "$BUILD/usr/lib/python3/dist-packages/"
find "$BUILD/usr/lib/python3/dist-packages" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$BUILD/usr/lib/python3/dist-packages" -type f -name '*.pyc' -delete
cp "$ROOT/linuxcnc-notify" "$BUILD/usr/bin/linuxcnc-notify"
chmod 755 "$BUILD/usr/bin/linuxcnc-notify"
cp "$ROOT/systemd/linuxcnc-notify.service" "$BUILD/lib/systemd/system/"
dpkg-deb --root-owner-group --build "$BUILD" "$OUT/linuxcnc-notify_${VERSION}_all.deb"
