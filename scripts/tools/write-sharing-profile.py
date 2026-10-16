#!/usr/bin/env python3
"""Atomically publish a private sharing profile without logging its bearer token."""

import json
import os
import sys
import tempfile
from pathlib import Path


def write_profile(path, endpoint, token):
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked sharing profile")
    if not token:
        raise ValueError("A sharing token is required")
    contents = (
        json.dumps(
            {
                "shareCredentialsVersion": 1,
                "endpoint": endpoint,
                "bearerToken": token,
            },
            indent=2,
        )
        + "\n"
    )
    fd, temporary = tempfile.mkstemp(prefix=".sharing-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(contents)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    try:
        write_profile(
            Path(sys.argv[1]), sys.argv[2], os.environ.get("DELTA_SHARING_TOKEN", "")
        )
    except (OSError, ValueError):
        print(
            "Cannot write private sharing profile; existing file preserved",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
