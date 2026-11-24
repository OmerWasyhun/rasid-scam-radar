"""Wrap the RASID Guardian APK in a Magisk module so it installs as a privileged system app.

Why: Android only lets privileged system apps record call audio (permission CAPTURE_AUDIO_OUTPUT). The module puts
the APK in /system/priv-app and whitelists that permission, without changing the real system partition.

Usage:  python tools/make_magisk_module.py path/to/rasid-guardian.apk  [out.zip]
Then on the rooted phone: uninstall any normal copy of the app, open Magisk -> Modules -> Install from storage ->
pick the zip -> Reboot.
"""
import sys
import zipfile
from pathlib import Path

PKG = "ae.rasid.rootguard"
NAME = "RasidGuardian"

MODULE_PROP = f"""id=rasid_guardian
name=RASID Call Guardian
version=v0.1
versionCode=1
author=RASID team
description=Installs RASID Guardian as a privileged app so it can listen to calls and end scam calls (hackathon test build).
"""

PRIVAPP_XML = f"""<?xml version="1.0" encoding="utf-8"?>
<permissions>
    <privapp-permissions package="{PKG}">
        <permission name="android.permission.CAPTURE_AUDIO_OUTPUT"/>
    </privapp-permissions>
</permissions>
"""

# Magisk's standard installer stub (module installs are handled by Magisk itself since v20.4)
UPDATE_BINARY = """#!/sbin/sh
umask 022
ui_print() { echo "$1"; }
OUTFD=$2
ZIPFILE=$3
. /data/adb/magisk/util_functions.sh
[ $MAGISK_VER_CODE -lt 20400 ] && abort "Please install Magisk v20.4+"
install_module
exit 0
"""


def build(apk: Path, out: Path) -> Path:
    if not apk.exists():
        raise SystemExit(f"APK not found: {apk}")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("module.prop", MODULE_PROP)
        z.writestr("META-INF/com/google/android/update-binary", UPDATE_BINARY)
        z.writestr("META-INF/com/google/android/updater-script", "#MAGISK\n")
        z.write(apk, f"system/priv-app/{NAME}/{NAME}.apk")
        z.writestr(f"system/etc/permissions/privapp-permissions-{PKG}.xml", PRIVAPP_XML)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    apk = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else apk.with_name("rasid-guardian-magisk.zip")
    print("Magisk module written to", build(apk, out))
