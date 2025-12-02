#!/usr/bin/env python3
"""
Migrate .md files to FalkorDB

Usage:
    python migrate_content.py

This script loads all .md files from the filesystem into FalkorDB
for use by the Vessels application.
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python.helpers.graph_store import GraphStore, MigrationHelper
from python.helpers.print_style import PrintStyle


async def main():
    print("=" * 60)
    print("Vessels Content Migration")
    print("=" * 60)
    print()

    # Initialize graph store
    print("Connecting to FalkorDB...")
    try:
        store = await GraphStore.get_instance()
        print("Connected successfully.")
    except Exception as e:
        print(f"ERROR: Failed to connect to FalkorDB: {e}")
        print()
        print("Make sure FalkorDB is running:")
        print("  docker compose up -d falkordb")
        return 1

    print()

    # Run migration
    print("Migrating .md files to FalkorDB...")
    print("-" * 60)

    try:
        count = await MigrationHelper.migrate_md_files_to_graph(store)
        print("-" * 60)
        print(f"SUCCESS: Migrated {count} files")
    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        return 1

    print()

    # Show stats
    print("Content statistics:")
    paths = await store.list_content()
    content_types = {}
    for path in paths:
        for prefix, ctype in [
            ("prompts/", "prompt"),
            ("agents/", "agent"),
            ("docs/", "doc"),
            ("instruments/", "instrument"),
            ("knowledge/", "knowledge"),
        ]:
            if path.startswith(prefix):
                content_types[ctype] = content_types.get(ctype, 0) + 1
                break
        else:
            content_types["other"] = content_types.get("other", 0) + 1

    for ctype, count in sorted(content_types.items()):
        print(f"  {ctype}: {count}")

    print()
    print("Migration complete!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
