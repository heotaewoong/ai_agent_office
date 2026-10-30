"""Explicit sidecar installer. Run as root on EC2 with two locally prepared tar archives.

Never reads office.env, office databases, model credentials, or htpasswd contents.
Preserves the existing nginx configuration bytes except one isolated location block.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import time

PIN = "f2139f04bc0916e4d8f10bbc257edfca57940c7a"
BASE = Path("/opt/heobrain-detail-lab")
CONFIG = Path("/etc/nginx/sites-enabled/heobrain-office")


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def extract(archive, destination):
    if destination.exists():
        raise RuntimeError("Release already exists; choose a new reviewed release ID")
    with tarfile.open(archive) as source:
        members = source.getmembers()
        for member in members:
            if not (member.isfile() or member.isdir()) or member.name.startswith("/") or ".." in Path(member.name).parts:
                raise RuntimeError("Unsafe archive entry")
        destination.mkdir(parents=True, mode=0o755)
        source.extractall(destination, filter="data")
    for path in destination.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-archive", required=True)
    parser.add_argument("--source-archive", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{40}", args.release):
        raise RuntimeError("Full reviewed commit SHA required")
    if hashlib.sha256(Path(args.source_archive).read_bytes()).hexdigest() != args.source_sha256:
        raise RuntimeError("Upstream archive integrity mismatch")
    previous = CONFIG.read_text()
    if "location ^~ /detail-lab/" in previous:
        raise RuntimeError("Lab route already exists; inspect existing installation before upgrading")
    root = re.search(r"location /\s*\{(.*?)\n\s*\}", previous, re.S)
    if not root:
        raise RuntimeError("Existing authenticated root location not found")
    auth = re.findall(r"^\s*(auth_basic(?:_user_file)?\s+[^;]+;)", root[1], re.M)
    if len(auth) != 2 or any(re.search(r"\boff\b", a) for a in auth):
        raise RuntimeError("Existing authentication must be preserved")
    release = BASE / "releases" / args.release
    upstream = BASE / "upstream" / PIN
    extract(args.app_archive, release)
    if not upstream.exists():
        extract(args.source_archive, upstream)
    if not (upstream / "plugins/machinebot-sangse-maker-mini/skills/machinebot-mini-detail-page/SKILL.md").is_file():
        raise RuntimeError("Pinned upstream skill missing")
    backup = BASE / ("nginx-before-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + ".conf")
    backup.write_text(previous)
    backup.chmod(0o600)
    block = "\n    location = /detail-lab { return 308 /detail-lab/; }\n    location ^~ /detail-lab/ {\n"
    block += "".join("        " + a + "\n" for a in auth)
    block += """        client_max_body_size 44m;
        limit_req zone=heobrain_office burst=20 nodelay;
        proxy_pass http://unix:/run/heobrain-detail-lab.sock:/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 20s;
    }
"""
    current = BASE / "current"
    if current.exists() or current.is_symlink():
        raise RuntimeError("Existing current release must be reviewed before replacing")
    current.symlink_to(release)
    for name in ("heobrain-detail-lab.socket", "heobrain-detail-lab.service"):
        target = Path("/etc/systemd/system") / name
        if target.exists():
            raise RuntimeError("Existing unit must be reviewed before replacing")
        target.write_bytes((release / name).read_bytes())
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "heobrain-detail-lab.socket")
    # Compare before mutation so another operator's nginx edits are never overwritten.
    if CONFIG.read_text() != previous:
        raise RuntimeError("Nginx changed concurrently; existing config left untouched")
    updated = previous[:root.start()] + block + previous[root.start():]
    CONFIG.write_text(updated)
    try:
        run("nginx", "-t")
        run("systemctl", "reload", "nginx")
    except BaseException:
        if CONFIG.read_text() == updated:
            CONFIG.write_text(previous)
            run("nginx", "-t")
            run("systemctl", "reload", "nginx")
        raise
    print(json.dumps({"release": args.release, "upstream": PIN, "config_backup": str(backup),
                      "existing_location_sha256": hashlib.sha256(root[0].encode()).hexdigest(),
                      "existing_app_restarted": False, "route": "/detail-lab/"}))


if __name__ == "__main__":
    main()
