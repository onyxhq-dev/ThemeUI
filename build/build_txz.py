#!/usr/bin/env python3
"""Build the ThemeUI package and point themeui.plg at it.

Usage:
    python3 build/build_txz.py              # rebuild the version already in themeui.plg
    python3 build/build_txz.py 2026.10.01a  # set a new version, then build

Writes archive/ThemeUI-<version>-noarch-1.txz and updates the version and
sha256 entities in themeui.plg so the two always match. Commit both together.

Python 3 standard library only, so it runs the same on Windows, macOS and
Linux. Every entry is owned by root:root with 755/644 modes, so installing
the package never changes the owner or mode of /usr or /usr/local on the
server, whatever machine it was built on.
"""
import hashlib
import io
import lzma
import pathlib
import re
import subprocess
import sys
import tarfile
import time

NAME = "ThemeUI"
ROOT = pathlib.Path(__file__).resolve().parent.parent
PLG = ROOT / "themeui.plg"
PLUGIN_DIR = f"usr/local/emhttp/plugins/{NAME}"

# (source in this repo, path inside the plugin directory, executable?)
FILES = [
    ("source/ThemeUILoader.page", "ThemeUILoader.page", False),
    ("source/ThemeUI.page", "ThemeUI.page", False),
    ("source/login-prepend.php", "login-prepend.php", False),
    ("source/event-started", "event/started", True),
    ("source/login-theme.sh", "scripts/login-theme.sh", True),
    ("assets/logo.png", "icon.png", False),
] + [
    (f"themes/{p.name}", f"themes/{p.name}", False)
    for p in sorted((ROOT / "themes").glob("*.css"))
]


def source_date():
    """Last commit time, so rebuilding the same commit gives the same bytes."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
        return int(out.stdout.strip())
    except (OSError, subprocess.CalledProcessError, ValueError):
        return int(time.time())


def entry(name, mtime, mode, data=None):
    info = tarfile.TarInfo(name)
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    info.mtime = mtime
    info.mode = mode
    if data is None:
        info.type = tarfile.DIRTYPE
    else:
        info.size = len(data)
    return info


def read(src):
    data = (ROOT / src).read_bytes()
    if not src.endswith(".png"):
        data = data.replace(b"\r\n", b"\n")  # a Windows checkout must not ship CRLF scripts
    return data


def main():
    plg = PLG.read_text(encoding="utf-8")
    m = re.search(r'<!ENTITY\s+version\s+"([^"]+)">', plg)
    if not m:
        sys.exit("themeui.plg has no version entity")
    version = sys.argv[1] if len(sys.argv) > 1 else m.group(1)
    if not re.fullmatch(r"[0-9A-Za-z._]+", version):
        sys.exit(f"bad version: {version!r}")

    mtime = source_date()
    members = {}
    for src, dest, executable in FILES:
        members[f"{PLUGIN_DIR}/{dest}"] = (read(src), 0o755 if executable else 0o644)

    dirs = set()
    for path in members:
        parts = path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for d in sorted(dirs):
            tar.addfile(entry(d + "/", mtime, 0o755))
        for path in sorted(members):
            data, mode = members[path]
            tar.addfile(entry(path, mtime, mode, data), io.BytesIO(data))

    pkg = f"{NAME}-{version}-noarch-1.txz"
    out = ROOT / "archive" / pkg
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(lzma.compress(buf.getvalue(), format=lzma.FORMAT_XZ,
                                  check=lzma.CHECK_CRC32, preset=9))
    sha256 = hashlib.sha256(out.read_bytes()).hexdigest()

    plg = re.sub(r'(<!ENTITY\s+version\s+")[^"]*(">)', rf"\g<1>{version}\g<2>", plg, count=1)
    plg, n = re.subn(r'(<!ENTITY\s+sha256\s+")[^"]*(">)', rf"\g<1>{sha256}\g<2>", plg, count=1)
    if n != 1:
        sys.exit("themeui.plg has no sha256 entity")
    with open(PLG, "w", encoding="utf-8", newline="\n") as f:
        f.write(plg)

    print(f"built   archive/{pkg} ({out.stat().st_size} bytes, {len(members)} files)")
    print(f"sha256  {sha256}")
    print("updated themeui.plg: version and sha256")
    print("next: add a <CHANGES> entry, then commit archive/ and themeui.plg together")


if __name__ == "__main__":
    main()
