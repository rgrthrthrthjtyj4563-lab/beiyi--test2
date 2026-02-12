import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel

from models import Statement, StatementItem, StatementSummary

_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"
DB_PATH = Path(os.getenv("SOA_DB_PATH", str(_DEFAULT_DB_PATH))).expanduser().resolve()
_DEFAULT_JSON_PATH = Path(__file__).resolve().parents[1] / "statements_db.json"
LEGACY_JSON_PATH = Path(os.getenv("STATEMENTS_JSON_PATH", str(_DEFAULT_JSON_PATH))).expanduser().resolve()
JSON_MIGRATION_KEY = "statements_json_to_sqlite_v1"


class StatementRecord(BaseModel):
    id: str
    status: str  # DRAFT, EXPORTED
    created_at: str
    updated_at: str
    statement: Statement
    history: List[dict]  # {timestamp, action, note}
    rule_template_name: Optional[str] = None
    rule_template_version: Optional[int] = None
    rule_strategy_name: Optional[str] = None
    engine_version: Optional[str] = None
    rule_snapshot_version: Optional[int] = None
    rule_snapshot: Optional[Dict] = None


class StatementManager:
    def __init__(self, db_path: Path = DB_PATH, legacy_json_path: Path = LEGACY_JSON_PATH):
        self.db_path = Path(db_path)
        self.legacy_json_path = Path(legacy_json_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_legacy_json_once()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS statements (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    customer TEXT NOT NULL,
                    period TEXT NOT NULL,
                    target_amount REAL NOT NULL,
                    summary_json TEXT NOT NULL,
                    rule_template_name TEXT,
                    rule_template_version INTEGER,
                    rule_strategy_name TEXT,
                    engine_version TEXT,
                    rule_snapshot_version INTEGER,
                    rule_snapshot_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS statement_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    statement_id TEXT NOT NULL,
                    item_order INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    name TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    amount REAL NOT NULL,
                    source TEXT NOT NULL,
                    quantity_mode TEXT NOT NULL DEFAULT 'ACTUAL_FULL',
                    actual_qty REAL NOT NULL DEFAULT 0,
                    billed_qty REAL NOT NULL DEFAULT 0,
                    unbilled_qty REAL NOT NULL DEFAULT 0,
                    decision_reason_code TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(statement_id) REFERENCES statements(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS statement_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    statement_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    note TEXT NOT NULL,
                    FOREIGN KEY(statement_id) REFERENCES statements(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS statement_migrations (
                    migration_key TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_statement_items_statement ON statement_items(statement_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_statement_history_statement ON statement_history(statement_id)")

            columns = [r["name"] for r in conn.execute("PRAGMA table_info(statements)").fetchall()]
            if "engine_version" not in columns:
                conn.execute("ALTER TABLE statements ADD COLUMN engine_version TEXT")
            if "rule_snapshot_version" not in columns:
                conn.execute("ALTER TABLE statements ADD COLUMN rule_snapshot_version INTEGER")
            if "rule_snapshot_json" not in columns:
                conn.execute("ALTER TABLE statements ADD COLUMN rule_snapshot_json TEXT")

            item_columns = [r["name"] for r in conn.execute("PRAGMA table_info(statement_items)").fetchall()]
            if "category" not in item_columns:
                conn.execute("ALTER TABLE statement_items ADD COLUMN category TEXT DEFAULT ''")
            if "billing_note" not in item_columns:
                conn.execute("ALTER TABLE statement_items ADD COLUMN billing_note TEXT DEFAULT ''")
            if "quantity_mode" not in item_columns:
                conn.execute("ALTER TABLE statement_items ADD COLUMN quantity_mode TEXT NOT NULL DEFAULT 'ACTUAL_FULL'")
            if "actual_qty" not in item_columns:
                conn.execute("ALTER TABLE statement_items ADD COLUMN actual_qty REAL NOT NULL DEFAULT 0")
            if "billed_qty" not in item_columns:
                conn.execute("ALTER TABLE statement_items ADD COLUMN billed_qty REAL NOT NULL DEFAULT 0")
            if "unbilled_qty" not in item_columns:
                conn.execute("ALTER TABLE statement_items ADD COLUMN unbilled_qty REAL NOT NULL DEFAULT 0")
            if "decision_reason_code" not in item_columns:
                conn.execute("ALTER TABLE statement_items ADD COLUMN decision_reason_code TEXT NOT NULL DEFAULT ''")

            conn.commit()

    def _migrate_legacy_json_once(self) -> None:
        with self._connect() as conn:
            done = conn.execute(
                "SELECT migration_key FROM statement_migrations WHERE migration_key = ?",
                (JSON_MIGRATION_KEY,),
            ).fetchone()
            if done:
                return

            if not self.legacy_json_path.exists():
                conn.execute(
                    "INSERT INTO statement_migrations (migration_key, applied_at) VALUES (?, ?)",
                    (JSON_MIGRATION_KEY, datetime.now().isoformat()),
                )
                conn.commit()
                return

            try:
                data = json.loads(self.legacy_json_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}

            for record_id, raw_record in (data or {}).items():
                try:
                    record = StatementRecord(**raw_record)
                except Exception:
                    continue

                existing = conn.execute("SELECT id FROM statements WHERE id = ?", (record_id,)).fetchone()
                if existing:
                    continue

                status = record.status if record.status in {"DRAFT", "EXPORTED"} else "DRAFT"
                conn.execute(
                    """
                    INSERT INTO statements (
                        id, status, customer, period, target_amount, summary_json,
                        rule_template_name, rule_template_version, rule_strategy_name, engine_version,
                        rule_snapshot_version, rule_snapshot_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        status,
                        record.statement.customer,
                        record.statement.period,
                        float(record.statement.target_amount),
                        json.dumps(
                            record.statement.summary.model_dump()
                            if hasattr(record.statement.summary, "model_dump")
                            else record.statement.summary.dict(),
                            ensure_ascii=False,
                        ),
                        record.rule_template_name,
                        record.rule_template_version,
                        record.rule_strategy_name,
                        json.dumps(record.rule_snapshot, ensure_ascii=False) if record.rule_snapshot else None,
                        record.created_at,
                        record.updated_at,
                    ),
                )

                for idx, item in enumerate(record.statement.items):
                    conn.execute(
                        """
                        INSERT INTO statement_items (
                            statement_id, item_order, level, name, unit, price, quantity, amount, source,
                            quantity_mode, actual_qty, billed_qty, unbilled_qty, decision_reason_code, category, billing_note
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record.id,
                            idx,
                            item.level,
                            item.name,
                            item.unit,
                            float(item.price),
                            float(item.quantity),
                            float(item.amount),
                            str(item.source),
                            str(getattr(item, "quantity_mode", "ACTUAL_FULL")),
                            float(getattr(item, "actual_qty", 0.0)),
                            float(getattr(item, "billed_qty", 0.0)),
                            float(getattr(item, "unbilled_qty", 0.0)),
                            str(getattr(item, "decision_reason_code", "")),
                            str(item.category),
                            str(item.billing_note),
                        ),
                    )

                for h in record.history:
                    conn.execute(
                        """
                        INSERT INTO statement_history (statement_id, timestamp, action, note)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            record.id,
                            str(h.get("timestamp", record.created_at)),
                            str(h.get("action", "CREATED")),
                            str(h.get("note", "")),
                        ),
                    )

            conn.execute(
                "INSERT INTO statement_migrations (migration_key, applied_at) VALUES (?, ?)",
                (JSON_MIGRATION_KEY, datetime.now().isoformat()),
            )
            conn.commit()

    def _build_record(self, conn: sqlite3.Connection, row: sqlite3.Row) -> StatementRecord:
        items_rows = conn.execute(
            """
            SELECT level, name, unit, price, quantity, amount, source, quantity_mode,
                   actual_qty, billed_qty, unbilled_qty, decision_reason_code, category, billing_note
            FROM statement_items
            WHERE statement_id = ?
            ORDER BY item_order ASC, id ASC
            """,
            (row["id"],),
        ).fetchall()
        items = [StatementItem(**dict(r)) for r in items_rows]

        history_rows = conn.execute(
            """
            SELECT timestamp, action, note
            FROM statement_history
            WHERE statement_id = ?
            ORDER BY id ASC
            """,
            (row["id"],),
        ).fetchall()
        history = [dict(r) for r in history_rows]

        summary = StatementSummary(**json.loads(row["summary_json"]))
        statement = Statement(
            customer=str(row["customer"]),
            period=str(row["period"]),
            target_amount=float(row["target_amount"]),
            summary=summary,
            items=items,
        )

        snapshot_raw = row["rule_snapshot_json"]
        return StatementRecord(
            id=str(row["id"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            statement=statement,
            history=history,
            rule_template_name=row["rule_template_name"],
            rule_template_version=int(row["rule_template_version"]) if row["rule_template_version"] is not None else None,
            rule_strategy_name=row["rule_strategy_name"],
            engine_version=row["engine_version"],
            rule_snapshot_version=int(row["rule_snapshot_version"]) if row["rule_snapshot_version"] is not None else None,
            rule_snapshot=json.loads(snapshot_raw) if snapshot_raw else None,
        )

    def create(
        self,
        statement: Statement,
        rule_template_name: Optional[str] = None,
        rule_template_version: Optional[int] = None,
        rule_strategy_name: Optional[str] = None,
        engine_version: Optional[str] = None,
        rule_snapshot_version: Optional[int] = None,
        rule_snapshot: Optional[Dict] = None,
    ) -> StatementRecord:
        stmt_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        status = "DRAFT"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO statements (
                    id, status, customer, period, target_amount, summary_json,
                    rule_template_name, rule_template_version, rule_strategy_name, engine_version,
                    rule_snapshot_version, rule_snapshot_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stmt_id,
                    status,
                    statement.customer,
                    statement.period,
                    float(statement.target_amount),
                    json.dumps(
                        statement.summary.model_dump()
                        if hasattr(statement.summary, "model_dump")
                        else statement.summary.dict(),
                        ensure_ascii=False,
                    ),
                    rule_template_name,
                    int(rule_template_version) if rule_template_version is not None else None,
                    rule_strategy_name,
                    engine_version,
                    int(rule_snapshot_version) if rule_snapshot_version is not None else None,
                    json.dumps(rule_snapshot, ensure_ascii=False) if rule_snapshot else None,
                    now,
                    now,
                ),
            )

            for idx, item in enumerate(statement.items):
                conn.execute(
                    """
                    INSERT INTO statement_items (
                        statement_id, item_order, level, name, unit, price, quantity, amount, source,
                        quantity_mode, actual_qty, billed_qty, unbilled_qty, decision_reason_code, category, billing_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stmt_id,
                        idx,
                        item.level,
                        item.name,
                        item.unit,
                        float(item.price),
                        float(item.quantity),
                        float(item.amount),
                        str(item.source),
                        str(item.quantity_mode),
                        float(item.actual_qty),
                        float(item.billed_qty),
                        float(item.unbilled_qty),
                        str(item.decision_reason_code),
                        str(item.category),
                        str(item.billing_note),
                    ),
                )

            conn.execute(
                """
                INSERT INTO statement_history (statement_id, timestamp, action, note)
                VALUES (?, ?, ?, ?)
                """,
                (stmt_id, now, "CREATED", "Initial generation"),
            )
            conn.commit()

        return self.get(stmt_id)

    def get(self, stmt_id: str) -> Optional[StatementRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM statements WHERE id = ?", (stmt_id,)).fetchone()
            if not row:
                return None
            return self._build_record(conn, row)

    def list(self) -> List[StatementRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM statements ORDER BY updated_at DESC, created_at DESC").fetchall()
            return [self._build_record(conn, row) for row in rows]

    def update_status(self, stmt_id: str, action: str, note: str = "") -> Optional[StatementRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT id, status FROM statements WHERE id = ?", (stmt_id,)).fetchone()
            if not row:
                return None

            current_status = str(row["status"])
            new_status = current_status
            if action == "export":
                if current_status in ["DRAFT", "EXPORTED"]:
                    new_status = "EXPORTED"
                else:
                    raise ValueError("Can only export DRAFT or EXPORTED statements")
            elif action == "reset":
                new_status = "DRAFT"
            else:
                raise ValueError("Unsupported action")

            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE statements SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, stmt_id),
            )
            conn.execute(
                """
                INSERT INTO statement_history (statement_id, timestamp, action, note)
                VALUES (?, ?, ?, ?)
                """,
                (stmt_id, now, action.upper(), note or ""),
            )
            conn.commit()

            row = conn.execute("SELECT * FROM statements WHERE id = ?", (stmt_id,)).fetchone()
            return self._build_record(conn, row)
