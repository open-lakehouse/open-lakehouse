#!/usr/bin/env python3
"""Require all Airflow 3 components to report healthy on stdin."""

import json
import sys


def main():
    try:
        health = json.load(sys.stdin)
        components = ("metadatabase", "scheduler", "triggerer", "dag_processor")
        return 0 if all(health[c]["status"] == "healthy" for c in components) else 1
    except (ValueError, KeyError, TypeError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
