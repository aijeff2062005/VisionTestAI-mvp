#!/usr/bin/env python3
"""List available local cameras."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.camera_utils import print_camera_list


def main() -> None:
    print_camera_list()


if __name__ == "__main__":
    main()
