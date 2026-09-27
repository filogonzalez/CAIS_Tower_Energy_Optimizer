"""Idempotently upload a generated snapshot to a governed UC Volume."""

from __future__ import annotations

import argparse
from pathlib import Path

from common.databricks_auth import get_workspace_client
from config.settings import get_settings


def upload_tree(local_root: Path, volume_root: str) -> int:
    client = get_workspace_client()
    uploaded = 0
    for path in sorted(local_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(local_root).as_posix()
        remote = f"{volume_root.rstrip('/')}/{local_root.name}/{relative}"
        with path.open("rb") as handle:
            client.files.upload(remote, handle, overwrite=True)
        uploaded += 1
    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    settings = get_settings()
    count = upload_tree(Path(args.snapshot), settings.volume_path)
    print(f"Uploaded {count} files to {settings.volume_path}/{Path(args.snapshot).name}")


if __name__ == "__main__":
    main()
