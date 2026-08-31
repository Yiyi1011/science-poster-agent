"""Conservative code-export check. Reports paths/rule names, never secret values.

This is a guardrail, not a claim to identify every possible credential. Raw logs,
account screenshots and live data must also stay out of the repository by policy.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "api_key_like": re.compile(rb"\bsk-(?:ws-)?[A-Za-z0-9_.-]{16,}"),
    "github_token_like": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})"),
    "cloud_access_key_like": re.compile(rb"\b(?:LTAI[A-Za-z0-9]{12,}|AKIA[A-Z0-9]{16})"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "signed_download_url": re.compile(rb"[?&](?:OSSAccessKeyId|x-oss-signature|X-Amz-Signature)="),
    "literal_bearer_token": re.compile(rb"Bearer\s+[A-Za-z0-9_.-]{24,}"),
}
PUBLIC_BINARY = {
    "frontend/public/solar-animation/media/narrated-v001-poster.png",
    "frontend/public/solar-animation/media/solar-messengers-narrated-v001.mp4",
}
FORBIDDEN_ROOTS = {"artifacts", "evidence", ".local-logs", "node_modules", ".venv", ".git"}


def path_is_private(name: str) -> bool:
    parts = name.replace("\\", "/").split("/")
    leaf = parts[-1].lower()
    return (any(part in FORBIDDEN_ROOTS for part in parts)
            or (leaf.startswith(".env") and leaf != ".env.example")
            or leaf == ".local-pids.json"
            or bool(re.search(r"\.(?:sqlite3?|db)(?:-.*)?$|\.(?:pem|key|p12|pfx|log|bundle)$", leaf)))


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def inspect(name: str, data: bytes) -> list[str]:
    findings = []
    if path_is_private(name):
        findings.append("private_path")
    if len(data) > 10 * 1024 * 1024:
        findings.append("oversize_file")
    if name in PUBLIC_BINARY:
        # These two repository-native demo assets have been inspected separately.
        return findings
    if b"\x00" in data:
        findings.append("unreviewed_binary")
    for label, pattern in PATTERNS.items():
        if pattern.search(data):
            findings.append(label)
    if name.endswith(".env.example"):
        safe = {"", "replace_me", "replace_with_your_key", "your_api_key_here", "your_api_key", "your_workspace_id", "your_app_id"}
        for line in data.decode("utf-8-sig").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            if re.search(r"(?:API_KEY|SECRET|TOKEN|PASSWORD)$", key.strip(), re.I) and value.strip().strip("\"'").lower() not in safe:
                findings.append("nonplaceholder_example_secret")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Inspect exact staged blobs; default inspects HEAD")
    args = parser.parse_args()
    names = (git("ls-files", "-z") if args.staged else git("ls-tree", "-r", "--name-only", "-z", "HEAD")).decode("utf-8").split("\0")
    findings, total, size = [], 0, 0
    for name in filter(None, names):
        data = git("show", (":" if args.staged else "HEAD:") + name)
        total += 1
        size += len(data)
        labels = inspect(name, data)
        if labels:
            findings.append({"path": name, "rules": labels})
    print(json.dumps({"status": "blocked" if findings else "passed", "scope": "index" if args.staged else "HEAD",
                      "files": total, "bytes": size, "findings": findings, "secret_values_printed": False}, ensure_ascii=False, indent=2))
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
