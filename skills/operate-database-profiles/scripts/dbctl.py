#!/usr/bin/env python3
"""Compatibility CLI entrypoint for the shared dbctl core."""

from __future__ import annotations

from dbctl_core import main


if __name__ == "__main__":
    raise SystemExit(main())
