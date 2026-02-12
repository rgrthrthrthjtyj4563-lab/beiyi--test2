#!/usr/bin/env python3
"""Backfill billing_mode from quantity_mode for historical inconsistent rows."""

import argparse
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "backend" / "data" / "app.db"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    mismatch_query = """
        SELECT id, name, quantity_mode, billing_mode
        FROM billing_items
        WHERE quantity_mode IN ('ACTUAL_FULL', 'ACTUAL_SELECTABLE', 'SIMULATED')
          AND (
                (quantity_mode = 'ACTUAL_FULL' AND billing_mode <> '固定入账')
             OR (quantity_mode = 'ACTUAL_SELECTABLE' AND billing_mode <> '智能择取')
             OR (quantity_mode = 'SIMULATED' AND billing_mode <> '模拟填充')
          )
        ORDER BY id
    """
    before = conn.execute(mismatch_query).fetchall()
    print(f"db={db_path}")
    print(f"mismatch_before={len(before)}")
    for row in before[:20]:
        print(
            f"id={row['id']} name={row['name']} "
            f"quantity_mode={row['quantity_mode']} billing_mode={row['billing_mode']}"
        )

    if not args.dry_run:
        conn.execute(
            """
            UPDATE billing_items
            SET billing_mode = CASE
                WHEN quantity_mode = 'ACTUAL_FULL' THEN '固定入账'
                WHEN quantity_mode = 'ACTUAL_SELECTABLE' THEN '智能择取'
                WHEN quantity_mode = 'SIMULATED' THEN '模拟填充'
                ELSE billing_mode
            END
            WHERE quantity_mode IN ('ACTUAL_FULL', 'ACTUAL_SELECTABLE', 'SIMULATED')
              AND (
                    (quantity_mode = 'ACTUAL_FULL' AND billing_mode <> '固定入账')
                 OR (quantity_mode = 'ACTUAL_SELECTABLE' AND billing_mode <> '智能择取')
                 OR (quantity_mode = 'SIMULATED' AND billing_mode <> '模拟填充')
              )
            """
        )
        conn.commit()

    after = conn.execute(mismatch_query).fetchall()
    print(f"mismatch_after={len(after)}")
    conn.close()


if __name__ == "__main__":
    main()
