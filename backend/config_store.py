import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"
DB_PATH = Path(os.getenv("SOA_DB_PATH", str(_DEFAULT_DB_PATH))).expanduser().resolve()

DEFAULT_RULE_TEMPLATE = {
    "template_name": "standard",
    "ratios": {"L1": 0.55, "L2": 0.30, "L3": 0.10, "L4": 0.05},
    "l4_max_ratio": 0.05,
    "ratio_warning_threshold": 0.15,
    "fill_order": ["L2", "L3", "L4"],
    "strategy_name": "equal_split_v1",
    "version": 1,
}

ALLOCATION_STRATEGIES = [
    {"key": "equal_split_v1", "label": "等额分摊策略"},
    {"key": "price_weighted_v1", "label": "按单价权重策略"},
]


VALID_LEVELS = ["L1", "L2", "L3", "L4"]


def _now_iso() -> str:
    return datetime.now().isoformat()


class ConfigStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE,
                    name TEXT NOT NULL,
                    level TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    unit TEXT NOT NULL,
                    price REAL NOT NULL DEFAULT 0,
                    is_existing INTEGER NOT NULL DEFAULT 0,
                    can_simulate INTEGER NOT NULL DEFAULT 0,
                    must_use INTEGER NOT NULL DEFAULT 0,
                    allow_discount INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    effective_from TEXT,
                    effective_to TEXT,
                    billing_note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = [r["name"] for r in conn.execute("PRAGMA table_info(billing_items)").fetchall()]
            if "category" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN category TEXT NOT NULL DEFAULT ''")
            if "billing_note" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN billing_note TEXT NOT NULL DEFAULT ''")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS statement_data_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    statement_id TEXT,
                    source_type TEXT NOT NULL,
                    source_name TEXT,
                    period TEXT,
                    no_data_reason TEXT,
                    rows_total INTEGER NOT NULL DEFAULT 0,
                    rows_used INTEGER NOT NULL DEFAULT 0,
                    matched_columns INTEGER NOT NULL DEFAULT 0,
                    unmatched_columns INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS field_mapping_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_name TEXT NOT NULL,
                    source_column TEXT NOT NULL,
                    target_item TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(template_name, source_column)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS allocation_rule_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_name TEXT NOT NULL UNIQUE,
                    ratios_json TEXT NOT NULL,
                    l4_max_ratio REAL NOT NULL DEFAULT 0.05,
                    ratio_warning_threshold REAL NOT NULL DEFAULT 0.15,
                    fill_order_json TEXT NOT NULL DEFAULT '["L2","L3","L4"]',
                    strategy_name TEXT NOT NULL DEFAULT 'equal_split_v1',
                    current_version INTEGER NOT NULL DEFAULT 1,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            rule_columns = [r["name"] for r in conn.execute("PRAGMA table_info(allocation_rule_templates)").fetchall()]
            if "strategy_name" not in rule_columns:
                conn.execute(
                    "ALTER TABLE allocation_rule_templates ADD COLUMN strategy_name TEXT NOT NULL DEFAULT 'equal_split_v1'"
                )
            if "current_version" not in rule_columns:
                conn.execute("ALTER TABLE allocation_rule_templates ADD COLUMN current_version INTEGER NOT NULL DEFAULT 1")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS allocation_rule_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    ratios_json TEXT NOT NULL,
                    l4_max_ratio REAL NOT NULL,
                    ratio_warning_threshold REAL NOT NULL,
                    fill_order_json TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(template_name, version)
                )
                """
            )

            self._ensure_default_rule(conn)
            self._backfill_rule_versions(conn)
            conn.commit()

    def _ensure_default_rule(self, conn: sqlite3.Connection) -> None:
        now = _now_iso()
        existing = conn.execute(
            "SELECT id FROM allocation_rule_templates WHERE template_name = ?",
            (DEFAULT_RULE_TEMPLATE["template_name"],),
        ).fetchone()
        if existing:
            return

        conn.execute(
            """
            INSERT INTO allocation_rule_templates (
                template_name,
                ratios_json,
                l4_max_ratio,
                ratio_warning_threshold,
                fill_order_json,
                strategy_name,
                current_version,
                is_active,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                DEFAULT_RULE_TEMPLATE["template_name"],
                json.dumps(DEFAULT_RULE_TEMPLATE["ratios"], ensure_ascii=False),
                DEFAULT_RULE_TEMPLATE["l4_max_ratio"],
                DEFAULT_RULE_TEMPLATE["ratio_warning_threshold"],
                json.dumps(DEFAULT_RULE_TEMPLATE["fill_order"], ensure_ascii=False),
                DEFAULT_RULE_TEMPLATE["strategy_name"],
                DEFAULT_RULE_TEMPLATE["version"],
                now,
                now,
            ),
        )

    def _backfill_rule_versions(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT template_name, ratios_json, l4_max_ratio, ratio_warning_threshold,
                   fill_order_json, strategy_name, current_version, created_at
            FROM allocation_rule_templates
            """
        ).fetchall()

        for row in rows:
            template_name = str(row["template_name"])
            current_version = int(row["current_version"] or 1)
            version_count = conn.execute(
                "SELECT COUNT(1) AS c FROM allocation_rule_versions WHERE template_name = ?",
                (template_name,),
            ).fetchone()["c"]
            if version_count <= 0:
                conn.execute(
                    """
                    INSERT INTO allocation_rule_versions (
                        template_name, version, ratios_json, l4_max_ratio,
                        ratio_warning_threshold, fill_order_json, strategy_name, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        template_name,
                        max(current_version, 1),
                        row["ratios_json"],
                        float(row["l4_max_ratio"]),
                        float(row["ratio_warning_threshold"]),
                        row["fill_order_json"],
                        str(row["strategy_name"] or "equal_split_v1"),
                        str(row["created_at"] or _now_iso()),
                    ),
                )
                continue

            max_version = conn.execute(
                "SELECT MAX(version) AS v FROM allocation_rule_versions WHERE template_name = ?",
                (template_name,),
            ).fetchone()["v"]
            if max_version and int(max_version) > current_version:
                conn.execute(
                    "UPDATE allocation_rule_templates SET current_version = ?, updated_at = ? WHERE template_name = ?",
                    (int(max_version), _now_iso(), template_name),
                )

    def list_billing_items(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM billing_items"
        params: List[Any] = []
        if not include_inactive:
            query += " WHERE status = ?"
            params.append("ACTIVE")
        query += " ORDER BY level, sort_order, id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def create_billing_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO billing_items (
                    code, name, level, category, unit, price, is_existing, can_simulate, must_use,
                    allow_discount, status, sort_order, effective_from,
                    effective_to, billing_note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("code"),
                    payload["name"],
                    payload["level"],
                    payload.get("category", ""),
                    payload["unit"],
                    payload["price"],
                    int(payload.get("is_existing", False)),
                    int(payload.get("can_simulate", False)),
                    int(payload.get("must_use", False)),
                    int(payload.get("allow_discount", False)),
                    payload.get("status", "ACTIVE"),
                    payload.get("sort_order", 0),
                    payload.get("effective_from"),
                    payload.get("effective_to"),
                    payload.get("billing_note", ""),
                    now,
                    now,
                ),
            )
            item_id = cursor.lastrowid
            conn.commit()
        return self.get_billing_item(item_id)

    def get_billing_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM billing_items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def update_billing_item(self, item_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_billing_item(item_id)
        if not existing:
            return None

        merged = {**existing, **payload, "updated_at": _now_iso()}
        values = [
            merged["code"],
            merged["name"],
            merged["level"],
            merged.get("category", ""),
            merged["unit"],
            merged["price"],
            int(bool(merged["is_existing"])),
            int(bool(merged["can_simulate"])),
            int(bool(merged["must_use"])),
            int(bool(merged["allow_discount"])),
            merged["status"],
            merged["sort_order"],
            merged["effective_from"],
            merged["effective_to"],
            merged.get("billing_note", ""),
            merged["updated_at"],
            item_id,
        ]
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE billing_items
                SET code = ?, name = ?, level = ?, category = ?, unit = ?, price = ?, is_existing = ?,
                    can_simulate = ?, must_use = ?, allow_discount = ?,
                    status = ?, sort_order = ?, effective_from = ?, effective_to = ?, billing_note = ?, updated_at = ?
                WHERE id = ?
                """,
                values,
            )
            conn.commit()
        return self.get_billing_item(item_id)

    def deactivate_billing_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        return self.update_billing_item(item_id, {"status": "INACTIVE"})

    def seed_billing_items(self, items: List[Dict[str, Any]]) -> None:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(1) AS c FROM billing_items").fetchone()["c"]
            if count > 0:
                return
            now = _now_iso()
            for idx, item in enumerate(items):
                conn.execute(
                    """
                    INSERT INTO billing_items (
                        code, name, level, category, unit, price, is_existing, can_simulate, must_use,
                        allow_discount, status, sort_order, effective_from,
                        effective_to, billing_note, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.get("code"),
                        item["name"],
                        item["level"],
                        item.get("category", ""),
                        item["unit"],
                        item["price"],
                        int(item.get("is_existing", False)),
                        int(item.get("can_simulate", False)),
                        int(item.get("must_use", False)),
                        int(item.get("allow_discount", False)),
                        item.get("status", "ACTIVE"),
                        item.get("sort_order", idx),
                        item.get("effective_from"),
                        item.get("effective_to"),
                        item.get("billing_note", ""),
                        now,
                        now,
                    ),
                )
            conn.commit()

    def backfill_item_meta(self, items: List[Dict[str, Any]]) -> int:
        meta_by_name = {}
        for item in items:
            name = item.get("name")
            if not name:
                continue
            meta_by_name[name] = {
                "category": item.get("category", "") or "",
                "billing_note": item.get("billing_note", "") or "",
            }

        updated = 0
        with self._connect() as conn:
            rows = conn.execute("SELECT id, name, category, billing_note FROM billing_items").fetchall()
            for row in rows:
                name = row["name"]
                src = meta_by_name.get(name)
                if not src:
                    continue
                current_category = row["category"] or ""
                current_note = row["billing_note"] or ""
                new_category = current_category or src["category"]
                new_note = current_note or src["billing_note"]
                if new_category != current_category or new_note != current_note:
                    conn.execute(
                        "UPDATE billing_items SET category = ?, billing_note = ?, updated_at = ? WHERE id = ?",
                        (new_category, new_note, _now_iso(), row["id"]),
                    )
                    updated += 1
            conn.commit()
        return updated

    def create_data_source(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO statement_data_sources (
                    statement_id, source_type, source_name, period, no_data_reason,
                    rows_total, rows_used, matched_columns, unmatched_columns, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("statement_id"),
                    payload["source_type"],
                    payload.get("source_name"),
                    payload.get("period"),
                    payload.get("no_data_reason"),
                    int(payload.get("rows_total", 0)),
                    int(payload.get("rows_used", 0)),
                    int(payload.get("matched_columns", 0)),
                    int(payload.get("unmatched_columns", 0)),
                    now,
                ),
            )
            row_id = cursor.lastrowid
            conn.commit()

        with self._connect() as conn:
            row = conn.execute("SELECT * FROM statement_data_sources WHERE id = ?", (row_id,)).fetchone()
        return dict(row)

    def list_statement_sources(self, statement_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM statement_data_sources WHERE statement_id = ? ORDER BY id DESC",
                (statement_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_field_mappings(self, template_name: str = "default") -> Dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_column, target_item
                FROM field_mapping_templates
                WHERE template_name = ? AND is_active = 1
                ORDER BY id ASC
                """,
                (template_name,),
            ).fetchall()
        return {str(r["source_column"]): str(r["target_item"]) for r in rows}

    def replace_field_mappings(self, template_name: str, mappings: Dict[str, str]) -> Dict[str, str]:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE field_mapping_templates SET is_active = 0, updated_at = ? WHERE template_name = ?",
                (now, template_name),
            )
            for source_column, target_item in mappings.items():
                source = str(source_column).strip()
                target = str(target_item).strip()
                if not source or not target:
                    continue
                conn.execute(
                    """
                    INSERT INTO field_mapping_templates (
                        template_name, source_column, target_item, is_active, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(template_name, source_column)
                    DO UPDATE SET target_item = excluded.target_item, is_active = 1, updated_at = excluded.updated_at
                    """,
                    (template_name, source, target, now, now),
                )
            conn.commit()
        return self.list_field_mappings(template_name=template_name)

    def list_allocation_strategies(self) -> List[Dict[str, str]]:
        return [dict(x) for x in ALLOCATION_STRATEGIES]

    def _normalize_rule_payload(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        data = dict(payload or {})
        template_name = str(data.get("template_name") or DEFAULT_RULE_TEMPLATE["template_name"]).strip() or DEFAULT_RULE_TEMPLATE["template_name"]

        raw_ratios = data.get("ratios") or DEFAULT_RULE_TEMPLATE["ratios"]
        ratios = {}
        for level in VALID_LEVELS:
            try:
                ratios[level] = float(raw_ratios.get(level, 0))
            except Exception:
                ratios[level] = 0.0

        try:
            l4_max_ratio = float(data.get("l4_max_ratio", DEFAULT_RULE_TEMPLATE["l4_max_ratio"]))
        except Exception:
            l4_max_ratio = float(DEFAULT_RULE_TEMPLATE["l4_max_ratio"])

        try:
            ratio_warning_threshold = float(data.get("ratio_warning_threshold", DEFAULT_RULE_TEMPLATE["ratio_warning_threshold"]))
        except Exception:
            ratio_warning_threshold = float(DEFAULT_RULE_TEMPLATE["ratio_warning_threshold"])

        raw_fill_order = data.get("fill_order") or DEFAULT_RULE_TEMPLATE["fill_order"]
        fill_order: List[str] = []
        for value in raw_fill_order:
            item = str(value).strip().upper()
            if item in VALID_LEVELS and item not in fill_order:
                fill_order.append(item)
        if not fill_order:
            fill_order = list(DEFAULT_RULE_TEMPLATE["fill_order"])

        strategy_name = str(data.get("strategy_name") or DEFAULT_RULE_TEMPLATE["strategy_name"]).strip() or DEFAULT_RULE_TEMPLATE["strategy_name"]
        if strategy_name not in {x["key"] for x in ALLOCATION_STRATEGIES}:
            strategy_name = DEFAULT_RULE_TEMPLATE["strategy_name"]

        return {
            "template_name": template_name,
            "ratios": ratios,
            "l4_max_ratio": l4_max_ratio,
            "ratio_warning_threshold": ratio_warning_threshold,
            "fill_order": fill_order,
            "strategy_name": strategy_name,
        }

    def get_allocation_rule(self, template_name: str = "standard") -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT template_name, ratios_json, l4_max_ratio, ratio_warning_threshold,
                       fill_order_json, strategy_name, current_version
                FROM allocation_rule_templates
                WHERE template_name = ? AND is_active = 1
                """,
                (template_name,),
            ).fetchone()

        if not row:
            return dict(DEFAULT_RULE_TEMPLATE)

        return {
            "template_name": str(row["template_name"]),
            "ratios": json.loads(row["ratios_json"]),
            "l4_max_ratio": float(row["l4_max_ratio"]),
            "ratio_warning_threshold": float(row["ratio_warning_threshold"]),
            "fill_order": json.loads(row["fill_order_json"]),
            "strategy_name": str(row["strategy_name"] or DEFAULT_RULE_TEMPLATE["strategy_name"]),
            "version": int(row["current_version"] or 1),
        }

    def list_allocation_rule_versions(self, template_name: str = "standard", limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT template_name, version, ratios_json, l4_max_ratio,
                       ratio_warning_threshold, fill_order_json, strategy_name, created_at
                FROM allocation_rule_versions
                WHERE template_name = ?
                ORDER BY version DESC
                LIMIT ?
                """,
                (template_name, safe_limit),
            ).fetchall()

        result = []
        for row in rows:
            result.append(
                {
                    "template_name": str(row["template_name"]),
                    "version": int(row["version"]),
                    "ratios": json.loads(row["ratios_json"]),
                    "l4_max_ratio": float(row["l4_max_ratio"]),
                    "ratio_warning_threshold": float(row["ratio_warning_threshold"]),
                    "fill_order": json.loads(row["fill_order_json"]),
                    "strategy_name": str(row["strategy_name"]),
                    "created_at": str(row["created_at"]),
                }
            )
        return result

    def upsert_allocation_rule(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        data = self._normalize_rule_payload(payload)

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT current_version, created_at FROM allocation_rule_templates WHERE template_name = ?",
                (data["template_name"],),
            ).fetchone()
            next_version = int(existing["current_version"]) + 1 if existing else 1
            created_at = str(existing["created_at"]) if existing else now

            conn.execute(
                """
                INSERT INTO allocation_rule_templates (
                    template_name, ratios_json, l4_max_ratio, ratio_warning_threshold,
                    fill_order_json, strategy_name, current_version, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(template_name)
                DO UPDATE SET
                    ratios_json = excluded.ratios_json,
                    l4_max_ratio = excluded.l4_max_ratio,
                    ratio_warning_threshold = excluded.ratio_warning_threshold,
                    fill_order_json = excluded.fill_order_json,
                    strategy_name = excluded.strategy_name,
                    current_version = excluded.current_version,
                    is_active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    data["template_name"],
                    json.dumps(data["ratios"], ensure_ascii=False),
                    data["l4_max_ratio"],
                    data["ratio_warning_threshold"],
                    json.dumps(data["fill_order"], ensure_ascii=False),
                    data["strategy_name"],
                    next_version,
                    created_at,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO allocation_rule_versions (
                    template_name, version, ratios_json, l4_max_ratio,
                    ratio_warning_threshold, fill_order_json, strategy_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["template_name"],
                    next_version,
                    json.dumps(data["ratios"], ensure_ascii=False),
                    data["l4_max_ratio"],
                    data["ratio_warning_threshold"],
                    json.dumps(data["fill_order"], ensure_ascii=False),
                    data["strategy_name"],
                    now,
                ),
            )
            conn.commit()

        return self.get_allocation_rule(template_name=data["template_name"])


config_store = ConfigStore()
