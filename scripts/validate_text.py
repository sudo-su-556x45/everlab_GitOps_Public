#!/usr/bin/env python3
"""Check repository text formatting independently of the Git diff."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".cfg",
    ".j2",
    ".json",
    ".json5",
    ".md",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".yaml",
    ".yml",
}
LEGACY_MISSING_FINAL_NEWLINE = {
    Path("kubernetes/applications/ai/faster-whisper/kustomization.yaml"),
    Path("kubernetes/applications/ai/faster-whisper/service.yaml"),
    Path("kubernetes/applications/ai/namespace.yaml"),
    Path("kubernetes/applications/home-assistant/kustomization.yaml"),
    Path("kubernetes/applications/unifi/application.yaml"),
    Path("kubernetes/applications/unifi/externalsecret.yaml"),
    Path("kubernetes/applications/unifi/kustomization.yaml"),
    Path("kubernetes/applications/unifi/mongo/application.yaml"),
    Path("kubernetes/applications/unifi/mongo/deployment.yaml"),
    Path("kubernetes/applications/unifi/mongo/init-configmap.yaml"),
    Path("kubernetes/applications/unifi/mongo/kustomization.yaml"),
    Path("kubernetes/applications/unifi/mongo/pvc.yaml"),
    Path("kubernetes/applications/unifi/mongo/service.yaml"),
    Path("kubernetes/applications/unifi/namespace.yaml"),
    Path("kubernetes/applications/unifi/unifi/application.yaml"),
    Path("kubernetes/applications/unifi/unifi/backendtlspolicy.yaml"),
    Path("kubernetes/applications/unifi/unifi/ca-configmap.yaml"),
    Path("kubernetes/applications/unifi/unifi/certificate.yaml"),
    Path("kubernetes/applications/unifi/unifi/deployment.yaml"),
    Path("kubernetes/applications/unifi/unifi/httproute.yaml"),
    Path("kubernetes/applications/unifi/unifi/kustomization.yaml"),
    Path("kubernetes/applications/unifi/unifi/lb-service.yaml"),
    Path("kubernetes/applications/unifi/unifi/pvc.yaml"),
    Path("kubernetes/applications/unifi/unifi/service.yaml"),
    Path("kubernetes/infrastructure/hardware-enablement/generic-device-plugin/application.yaml"),
    Path("kubernetes/infrastructure/hardware-enablement/generic-device-plugin/info.md"),
    Path("kubernetes/infrastructure/hardware-enablement/generic-device-plugin/kustomization.yaml"),
    Path("kubernetes/infrastructure/hardware-enablement/kustomization.yaml"),
    Path("kubernetes/infrastructure/metrics-server/kustomization.yaml"),
    Path("kubernetes/infrastructure/openebs-localpv/kustomization.yaml"),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def main() -> int:
    errors: list[str] = []
    checked = 0
    for path in tracked_files():
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        checked += 1
        relative_path = path.relative_to(ROOT)
        if text and not text.endswith("\n") and relative_path not in LEGACY_MISSING_FINAL_NEWLINE:
            errors.append(f"{relative_path}: missing final newline")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.rstrip(" \t") != line:
                errors.append(f"{relative_path}:{line_number}: trailing whitespace")
            if path.suffix.lower() in {".yaml", ".yml"} and "\t" in line:
                errors.append(f"{relative_path}:{line_number}: tab in YAML")

    if errors:
        print("Text validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Text validation passed for {checked} tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
