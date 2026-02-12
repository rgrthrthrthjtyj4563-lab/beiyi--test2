import json
import math
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
    "selection_strategy": "priority_greedy_v1",
    "enabled_item_ids": [],
    "tail_diff_threshold": 0.0,
    "fallback_l3_item_id": None,
    "max_simulation_ratio": 1.0,
    "version": 1,
}

ALLOCATION_STRATEGIES = [
    {"key": "equal_split_v1", "label": "等额分摊策略"},
    {"key": "price_weighted_v1", "label": "按单价权重策略"},
    {"key": "priority_greedy_v1", "label": "优先级贪心策略"},
]


VALID_LEVELS = ["L1", "L2", "L3", "L4"]
VALID_STATUS = {"启用", "停用", "ACTIVE", "INACTIVE"}
VALID_BILLING_MODES = {"固定入账", "智能择取", "模拟填充"}
VALID_QUANTITY_MODES = {"ACTUAL_FULL", "ACTUAL_SELECTABLE", "SIMULATED", "MANUAL"}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _to_int_flag(val: Any, default: int = 0) -> int:
    try:
        return int(bool(val))
    except Exception:
        return int(default)


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        x = float(val)
        if math.isnan(x) or math.isinf(x):
            return float(default)
        return x
    except Exception:
        return float(default)


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except Exception:
        return int(default)


def _safe_text(val: Any, default: str = "") -> str:
    if val is None:
        return default
    text = str(val).strip()
    return text if text else default


def _normalize_status(raw_status: Any) -> str:
    status = _safe_text(raw_status, "启用")
    if status == "ACTIVE":
        return "启用"
    if status == "INACTIVE":
        return "停用"
    if status in {"启用", "停用"}:
        return status
    return "启用"


def _derive_billing_mode(payload: Dict[str, Any]) -> str:
    mode = _safe_text(payload.get("billing_mode"), "")
    if mode in VALID_BILLING_MODES:
        return mode

    quantity_mode = _safe_text(payload.get("quantity_mode"), "").upper()
    if quantity_mode == "ACTUAL_FULL":
        return "固定入账"
    if quantity_mode == "ACTUAL_SELECTABLE":
        return "智能择取"
    if quantity_mode == "SIMULATED":
        return "模拟填充"
    return "智能择取"


def _derive_quantity_mode(payload: Dict[str, Any]) -> str:
    raw_mode = str(payload.get("quantity_mode", "") or "").strip().upper()
    if raw_mode in {"ACTUAL_FULL", "ACTUAL_SELECTABLE", "SIMULATED", "MANUAL"}:
        return raw_mode

    if bool(payload.get("can_simulate", False)):
        return "SIMULATED"
    return "ACTUAL_FULL"


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
                    is_enabled_default INTEGER NOT NULL DEFAULT 1,
                    quantity_mode TEXT NOT NULL DEFAULT 'ACTUAL_FULL',
                    min_pick_ratio REAL NOT NULL DEFAULT 0,
                    max_pick_ratio REAL NOT NULL DEFAULT 1,
                    pick_priority INTEGER NOT NULL DEFAULT 100,
                    report_required INTEGER NOT NULL DEFAULT 0,
                    tail_balance_eligible INTEGER NOT NULL DEFAULT 0,
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
            
            # V2.0 新增字段
            if "billing_mode" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN billing_mode TEXT NOT NULL DEFAULT '智能择取'")
            if "require_business_data" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN require_business_data INTEGER NOT NULL DEFAULT 1")
            
            # 旧字段保留用于兼容
            if "category" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN category TEXT NOT NULL DEFAULT ''")
            if "billing_note" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN billing_note TEXT NOT NULL DEFAULT ''")
            if "is_enabled_default" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN is_enabled_default INTEGER NOT NULL DEFAULT 1")
            if "quantity_mode" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN quantity_mode TEXT NOT NULL DEFAULT 'ACTUAL_FULL'")
            if "min_pick_ratio" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN min_pick_ratio REAL NOT NULL DEFAULT 0")
            if "max_pick_ratio" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN max_pick_ratio REAL NOT NULL DEFAULT 1")
            if "pick_priority" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN pick_priority INTEGER NOT NULL DEFAULT 100")
            if "report_required" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN report_required INTEGER NOT NULL DEFAULT 0")
            if "tail_balance_eligible" not in columns:
                conn.execute("ALTER TABLE billing_items ADD COLUMN tail_balance_eligible INTEGER NOT NULL DEFAULT 0")
            
            # 数据迁移：将旧 quantity_mode 映射到新 billing_mode
            conn.execute(
                """
                UPDATE billing_items
                SET billing_mode = CASE
                    WHEN quantity_mode = 'ACTUAL_FULL' THEN '固定入账'
                    WHEN quantity_mode = 'ACTUAL_SELECTABLE' THEN '智能择取'
                    WHEN quantity_mode = 'SIMULATED' THEN '模拟填充'
                    ELSE '智能择取'
                END
                WHERE billing_mode IS NULL OR billing_mode = ''
                """
            )

            # 数据修复：历史数据中可能存在 quantity_mode 与 billing_mode 不一致。
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
            
            # 根据层级设置默认优先级
            conn.execute(
                """
                UPDATE billing_items
                SET pick_priority = CASE level
                    WHEN 'L1' THEN 10
                    WHEN 'L2' THEN 50
                    WHEN 'L3' THEN 100
                    WHEN 'L4' THEN 200
                    ELSE 100
                END
                WHERE pick_priority = 100 OR pick_priority IS NULL
                """
            )
            
            # 将 status 从英文转换为中文
            conn.execute(
                """
                UPDATE billing_items
                SET status = CASE
                    WHEN status = 'ACTIVE' THEN '启用'
                    WHEN status = 'INACTIVE' THEN '停用'
                    ELSE '启用'
                END
                WHERE status IN ('ACTIVE', 'INACTIVE')
                """
            )

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
                    selection_strategy TEXT NOT NULL DEFAULT 'priority_greedy_v1',
                    enabled_item_ids_json TEXT NOT NULL DEFAULT '[]',
                    tail_diff_threshold REAL NOT NULL DEFAULT 0,
                    fallback_l3_item_id INTEGER,
                    max_simulation_ratio REAL NOT NULL DEFAULT 1,
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
            if "selection_strategy" not in rule_columns:
                conn.execute(
                    "ALTER TABLE allocation_rule_templates ADD COLUMN selection_strategy TEXT NOT NULL DEFAULT 'priority_greedy_v1'"
                )
            if "enabled_item_ids_json" not in rule_columns:
                conn.execute("ALTER TABLE allocation_rule_templates ADD COLUMN enabled_item_ids_json TEXT NOT NULL DEFAULT '[]'")
            if "tail_diff_threshold" not in rule_columns:
                conn.execute("ALTER TABLE allocation_rule_templates ADD COLUMN tail_diff_threshold REAL NOT NULL DEFAULT 0")
            if "fallback_l3_item_id" not in rule_columns:
                conn.execute("ALTER TABLE allocation_rule_templates ADD COLUMN fallback_l3_item_id INTEGER")
            if "max_simulation_ratio" not in rule_columns:
                conn.execute("ALTER TABLE allocation_rule_templates ADD COLUMN max_simulation_ratio REAL NOT NULL DEFAULT 1")
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
                    selection_strategy TEXT NOT NULL DEFAULT 'priority_greedy_v1',
                    enabled_item_ids_json TEXT NOT NULL DEFAULT '[]',
                    tail_diff_threshold REAL NOT NULL DEFAULT 0,
                    fallback_l3_item_id INTEGER,
                    max_simulation_ratio REAL NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(template_name, version)
                )
                """
            )
            rule_version_columns = [r["name"] for r in conn.execute("PRAGMA table_info(allocation_rule_versions)").fetchall()]
            if "selection_strategy" not in rule_version_columns:
                conn.execute(
                    "ALTER TABLE allocation_rule_versions ADD COLUMN selection_strategy TEXT NOT NULL DEFAULT 'priority_greedy_v1'"
                )
            if "enabled_item_ids_json" not in rule_version_columns:
                conn.execute("ALTER TABLE allocation_rule_versions ADD COLUMN enabled_item_ids_json TEXT NOT NULL DEFAULT '[]'")
            if "tail_diff_threshold" not in rule_version_columns:
                conn.execute("ALTER TABLE allocation_rule_versions ADD COLUMN tail_diff_threshold REAL NOT NULL DEFAULT 0")
            if "fallback_l3_item_id" not in rule_version_columns:
                conn.execute("ALTER TABLE allocation_rule_versions ADD COLUMN fallback_l3_item_id INTEGER")
            if "max_simulation_ratio" not in rule_version_columns:
                conn.execute("ALTER TABLE allocation_rule_versions ADD COLUMN max_simulation_ratio REAL NOT NULL DEFAULT 1")

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
                selection_strategy,
                enabled_item_ids_json,
                tail_diff_threshold,
                fallback_l3_item_id,
                max_simulation_ratio,
                current_version,
                is_active,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                DEFAULT_RULE_TEMPLATE["template_name"],
                json.dumps(DEFAULT_RULE_TEMPLATE["ratios"], ensure_ascii=False),
                DEFAULT_RULE_TEMPLATE["l4_max_ratio"],
                DEFAULT_RULE_TEMPLATE["ratio_warning_threshold"],
                json.dumps(DEFAULT_RULE_TEMPLATE["fill_order"], ensure_ascii=False),
                DEFAULT_RULE_TEMPLATE["strategy_name"],
                DEFAULT_RULE_TEMPLATE["selection_strategy"],
                json.dumps(DEFAULT_RULE_TEMPLATE["enabled_item_ids"], ensure_ascii=False),
                DEFAULT_RULE_TEMPLATE["tail_diff_threshold"],
                DEFAULT_RULE_TEMPLATE["fallback_l3_item_id"],
                DEFAULT_RULE_TEMPLATE["max_simulation_ratio"],
                DEFAULT_RULE_TEMPLATE["version"],
                now,
                now,
            ),
        )

    def _backfill_rule_versions(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT template_name, ratios_json, l4_max_ratio, ratio_warning_threshold,
                   fill_order_json, strategy_name, selection_strategy, enabled_item_ids_json,
                   tail_diff_threshold, fallback_l3_item_id, max_simulation_ratio, current_version, created_at
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
                        ratio_warning_threshold, fill_order_json, strategy_name,
                        selection_strategy, enabled_item_ids_json, tail_diff_threshold,
                        fallback_l3_item_id, max_simulation_ratio, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        template_name,
                        max(current_version, 1),
                        row["ratios_json"],
                        float(row["l4_max_ratio"]),
                        float(row["ratio_warning_threshold"]),
                        row["fill_order_json"],
                        str(row["strategy_name"] or "equal_split_v1"),
                        str(row["selection_strategy"] or "priority_greedy_v1"),
                        str(row["enabled_item_ids_json"] or "[]"),
                        float(row["tail_diff_threshold"] or 0.0),
                        int(row["fallback_l3_item_id"]) if row["fallback_l3_item_id"] is not None else None,
                        float(row["max_simulation_ratio"] or 1.0),
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

    def _normalize_billing_item_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(row or {})
        item_id = _safe_int(item.get("id"), 0)

        level = _safe_text(item.get("level"), "").upper()
        if level not in VALID_LEVELS:
            level = "L3"
        item["level"] = level

        item["name"] = _safe_text(item.get("name"), f"未命名计费项-{item_id or 'NEW'}")
        item["unit"] = _safe_text(item.get("unit"), "元/次")
        item["category"] = _safe_text(item.get("category"), "")
        item["billing_note"] = _safe_text(item.get("billing_note"), "")
        item["code"] = _safe_text(item.get("code"), "") or None

        item["price"] = _safe_float(item.get("price"), 0.0)
        item["sort_order"] = _safe_int(item.get("sort_order"), 0)
        item["pick_priority"] = _safe_int(
            item.get("pick_priority"),
            {"L1": 10, "L2": 50, "L3": 100, "L4": 200}.get(level, 100),
        )

        item["is_existing"] = bool(_to_int_flag(item.get("is_existing", False)))
        item["can_simulate"] = bool(_to_int_flag(item.get("can_simulate", False)))
        item["must_use"] = bool(_to_int_flag(item.get("must_use", False)))
        item["is_enabled_default"] = bool(_to_int_flag(item.get("is_enabled_default", True), default=1))
        item["report_required"] = bool(_to_int_flag(item.get("report_required", False)))
        item["tail_balance_eligible"] = bool(_to_int_flag(item.get("tail_balance_eligible", False)))
        item["allow_discount"] = bool(_to_int_flag(item.get("allow_discount", False)))
        item["require_business_data"] = bool(_to_int_flag(item.get("require_business_data", True), default=1))

        item["status"] = _normalize_status(item.get("status"))

        quantity_mode = _safe_text(item.get("quantity_mode"), "").upper()
        if quantity_mode not in VALID_QUANTITY_MODES:
            quantity_mode = _derive_quantity_mode(item)
        item["quantity_mode"] = quantity_mode

        item["billing_mode"] = _derive_billing_mode(item)
        if item["billing_mode"] not in VALID_BILLING_MODES:
            item["billing_mode"] = "智能择取"

        min_pick = max(0.0, min(_safe_float(item.get("min_pick_ratio"), 0.0), 1.0))
        max_pick = max(0.0, min(_safe_float(item.get("max_pick_ratio"), 1.0), 1.0))
        if min_pick > max_pick:
            min_pick, max_pick = max_pick, min_pick
        item["min_pick_ratio"] = min_pick
        item["max_pick_ratio"] = max_pick

        item["effective_from"] = _safe_text(item.get("effective_from"), "") or None
        item["effective_to"] = _safe_text(item.get("effective_to"), "") or None
        item["created_at"] = _safe_text(item.get("created_at"), _now_iso())
        item["updated_at"] = _safe_text(item.get("updated_at"), item["created_at"])
        if item_id:
            item["id"] = item_id
        return item

    def list_billing_items(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM billing_items"
        params: List[Any] = []
        if not include_inactive:
            query += " WHERE status IN (?, ?, '') OR status IS NULL"
            params.extend(["启用", "ACTIVE"])
        query += " ORDER BY level, sort_order, id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._normalize_billing_item_row(dict(r)) for r in rows]

    def create_billing_item(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        now = _now_iso()
        normalized_payload = self._normalize_billing_item_row({**payload, "created_at": now, "updated_at": now})

        # 根据层级设置默认优先级
        level = normalized_payload.get("level", "L3")
        default_priority = {"L1": 10, "L2": 50, "L3": 100, "L4": 200}.get(level, 100)
        
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO billing_items (
                    code, name, level, category, unit, price, billing_mode, pick_priority, require_business_data,
                    is_existing, can_simulate, must_use, is_enabled_default, quantity_mode, min_pick_ratio, max_pick_ratio,
                    report_required, tail_balance_eligible, allow_discount, status, sort_order, effective_from,
                    effective_to, billing_note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_payload.get("code"),
                    normalized_payload["name"],
                    level,
                    normalized_payload.get("category", ""),
                    normalized_payload["unit"],
                    normalized_payload["price"],
                    normalized_payload.get("billing_mode", "智能择取"),  # V2.0 新字段
                    int(normalized_payload.get("pick_priority", default_priority) or default_priority),  # V2.0 新字段
                    _to_int_flag(normalized_payload.get("require_business_data", True)),  # V2.0 新字段
                    # 旧字段保留用于兼容
                    int(normalized_payload.get("is_existing", False)),
                    _to_int_flag(normalized_payload.get("can_simulate", False)),
                    _to_int_flag(normalized_payload.get("must_use", False)),
                    _to_int_flag(normalized_payload.get("is_enabled_default", True), default=1),
                    _derive_quantity_mode(normalized_payload),
                    float(normalized_payload.get("min_pick_ratio", 0.0) or 0.0),
                    float(normalized_payload.get("max_pick_ratio", 1.0) or 1.0),
                    _to_int_flag(normalized_payload.get("report_required", False)),
                    _to_int_flag(normalized_payload.get("tail_balance_eligible", False)),
                    int(normalized_payload.get("allow_discount", False)),
                    _normalize_status(normalized_payload.get("status", "启用")),
                    normalized_payload.get("sort_order", 0),
                    normalized_payload.get("effective_from"),
                    normalized_payload.get("effective_to"),
                    normalized_payload.get("billing_note", ""),
                    now,
                    now,
                ),
            )
            item_id = cursor.lastrowid
            conn.commit()
        if item_id is None:
            return None
        # 类型断言：item_id 在成功插入后不会是 None
        assert item_id is not None
        return self.get_billing_item(item_id)

    def get_billing_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM billing_items WHERE id = ?", (item_id,)).fetchone()
        return self._normalize_billing_item_row(dict(row)) if row else None

    def update_billing_item(self, item_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_billing_item(item_id)
        if not existing:
            return None

        merged = self._normalize_billing_item_row({**existing, **payload, "updated_at": _now_iso()})
        merged["quantity_mode"] = _derive_quantity_mode(merged)
        
        # 确保 billing_mode 有值
        if not merged.get("billing_mode"):
            merged["billing_mode"] = "智能择取"
        
        values = [
            merged["code"],
            merged["name"],
            merged["level"],
            merged.get("category", ""),
            merged["unit"],
            merged["price"],
            merged.get("billing_mode", "智能择取"),  # V2.0 新字段
            int(merged.get("pick_priority", 100) or 100),  # V2.0 新字段
            _to_int_flag(merged.get("require_business_data", True)),  # V2.0 新字段
            # 旧字段保留用于兼容
            int(bool(merged["is_existing"])),
            _to_int_flag(merged["can_simulate"]),
            _to_int_flag(merged["must_use"]),
            _to_int_flag(merged.get("is_enabled_default", True), default=1),
            merged["quantity_mode"],
            float(merged.get("min_pick_ratio", 0.0) or 0.0),
            float(merged.get("max_pick_ratio", 1.0) or 1.0),
            _to_int_flag(merged.get("report_required", False)),
            _to_int_flag(merged.get("tail_balance_eligible", False)),
            int(bool(merged["allow_discount"])),
            _normalize_status(merged["status"]),
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
                SET code = ?, name = ?, level = ?, category = ?, unit = ?, price = ?, billing_mode = ?,
                    pick_priority = ?, require_business_data = ?, is_existing = ?, can_simulate = ?, must_use = ?,
                    is_enabled_default = ?, quantity_mode = ?, min_pick_ratio = ?, max_pick_ratio = ?,
                    report_required = ?, tail_balance_eligible = ?, allow_discount = ?, status = ?, sort_order = ?,
                    effective_from = ?, effective_to = ?, billing_note = ?, updated_at = ?
                WHERE id = ?
                """,
                values,
            )
            conn.commit()
        return self.get_billing_item(item_id)

    def deactivate_billing_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """停用计费项（中文状态）"""
        return self.update_billing_item(item_id, {"status": "停用"})

    def activate_billing_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """启用计费项（中文状态）"""
        return self.update_billing_item(item_id, {"status": "启用"})

    def delete_billing_item(self, item_id: int) -> bool:
        """物理删除计费项"""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM billing_items WHERE id = ?", (item_id,))
            conn.commit()
            return cursor.rowcount > 0

    def batch_update_billing_items(self, item_ids: List[int], updates: Dict[str, Any]) -> int:
        """批量更新计费项"""
        if not item_ids:
            return 0
        
        # 构建更新字段
        allowed_fields = {"billing_mode", "pick_priority", "require_business_data", "status", "price", "unit", "billing_note"}
        update_fields = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not update_fields:
            return 0
        
        set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
        values = list(update_fields.values())
        values.append(_now_iso())  # updated_at
        
        # 构建IN子句
        placeholders = ", ".join(["?"] * len(item_ids))
        values.extend(item_ids)
        
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE billing_items
                SET {set_clause}, updated_at = ?
                WHERE id IN ({placeholders})
                """,
                values,
            )
            conn.commit()
            return cursor.rowcount

    def batch_delete_billing_items(self, item_ids: List[int]) -> int:
        """批量物理删除计费项"""
        if not item_ids:
            return 0
        
        placeholders = ", ".join(["?"] * len(item_ids))
        
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM billing_items WHERE id IN ({placeholders})",
                item_ids,
            )
            conn.commit()
            return cursor.rowcount

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
                        is_enabled_default, quantity_mode, min_pick_ratio, max_pick_ratio, pick_priority,
                        report_required, tail_balance_eligible,
                        allow_discount, status, sort_order, effective_from,
                        effective_to, billing_note, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.get("code"),
                        item["name"],
                        item["level"],
                        item.get("category", ""),
                        item["unit"],
                        item["price"],
                        int(item.get("is_existing", False)),
                        _to_int_flag(item.get("can_simulate", False)),
                        _to_int_flag(item.get("must_use", False)),
                        _to_int_flag(item.get("is_enabled_default", True), default=1),
                        _derive_quantity_mode(item),
                        float(item.get("min_pick_ratio", 0.0) or 0.0),
                        float(item.get("max_pick_ratio", 1.0) or 1.0),
                        int(item.get("pick_priority", 100) or 100),
                        _to_int_flag(item.get("report_required", False)),
                        _to_int_flag(item.get("tail_balance_eligible", False)),
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
                    statement_id, source_type, source_name, period,
                    rows_total, rows_used, matched_columns, unmatched_columns, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("statement_id"),
                    payload["source_type"],
                    payload.get("source_name"),
                    payload.get("period"),
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
                """
                SELECT id, statement_id, source_type, source_name, period,
                       rows_total, rows_used, matched_columns, unmatched_columns, created_at
                FROM statement_data_sources
                WHERE statement_id = ?
                ORDER BY id DESC
                """,
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
        selection_strategy = str(data.get("selection_strategy") or DEFAULT_RULE_TEMPLATE["selection_strategy"]).strip() or DEFAULT_RULE_TEMPLATE["selection_strategy"]
        if selection_strategy not in {x["key"] for x in ALLOCATION_STRATEGIES}:
            selection_strategy = DEFAULT_RULE_TEMPLATE["selection_strategy"]
        raw_enabled = data.get("enabled_item_ids") or DEFAULT_RULE_TEMPLATE["enabled_item_ids"]
        enabled_item_ids: List[int] = []
        for item_id in raw_enabled:
            try:
                enabled_item_ids.append(int(item_id))
            except Exception:
                continue
        try:
            tail_diff_threshold = float(data.get("tail_diff_threshold", DEFAULT_RULE_TEMPLATE["tail_diff_threshold"]))
        except Exception:
            tail_diff_threshold = float(DEFAULT_RULE_TEMPLATE["tail_diff_threshold"])
        fallback_l3_item_id = data.get("fallback_l3_item_id")
        try:
            fallback_l3_item_id = int(fallback_l3_item_id) if fallback_l3_item_id is not None else None
        except Exception:
            fallback_l3_item_id = None
        try:
            max_simulation_ratio = float(data.get("max_simulation_ratio", DEFAULT_RULE_TEMPLATE["max_simulation_ratio"]))
        except Exception:
            max_simulation_ratio = float(DEFAULT_RULE_TEMPLATE["max_simulation_ratio"])
        max_simulation_ratio = max(0.0, min(max_simulation_ratio, 1.0))

        return {
            "template_name": template_name,
            "ratios": ratios,
            "l4_max_ratio": l4_max_ratio,
            "ratio_warning_threshold": ratio_warning_threshold,
            "fill_order": fill_order,
            "strategy_name": strategy_name,
            "selection_strategy": selection_strategy,
            "enabled_item_ids": enabled_item_ids,
            "tail_diff_threshold": max(tail_diff_threshold, 0.0),
            "fallback_l3_item_id": fallback_l3_item_id,
            "max_simulation_ratio": max_simulation_ratio,
        }

    def get_allocation_rule(self, template_name: str = "standard") -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT template_name, ratios_json, l4_max_ratio, ratio_warning_threshold,
                       fill_order_json, strategy_name, selection_strategy, enabled_item_ids_json,
                       tail_diff_threshold, fallback_l3_item_id, max_simulation_ratio, current_version
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
            "selection_strategy": str(row["selection_strategy"] or DEFAULT_RULE_TEMPLATE["selection_strategy"]),
            "enabled_item_ids": json.loads(row["enabled_item_ids_json"] or "[]"),
            "tail_diff_threshold": float(row["tail_diff_threshold"] or 0.0),
            "fallback_l3_item_id": int(row["fallback_l3_item_id"]) if row["fallback_l3_item_id"] is not None else None,
            "max_simulation_ratio": float(row["max_simulation_ratio"] or 1.0),
            "version": int(row["current_version"] or 1),
        }

    def list_allocation_rule_versions(self, template_name: str = "standard", limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT template_name, version, ratios_json, l4_max_ratio,
                       ratio_warning_threshold, fill_order_json, strategy_name,
                       selection_strategy, enabled_item_ids_json, tail_diff_threshold,
                       fallback_l3_item_id, max_simulation_ratio, created_at
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
                    "selection_strategy": str(row["selection_strategy"] or DEFAULT_RULE_TEMPLATE["selection_strategy"]),
                    "enabled_item_ids": json.loads(row["enabled_item_ids_json"] or "[]"),
                    "tail_diff_threshold": float(row["tail_diff_threshold"] or 0.0),
                    "fallback_l3_item_id": int(row["fallback_l3_item_id"]) if row["fallback_l3_item_id"] is not None else None,
                    "max_simulation_ratio": float(row["max_simulation_ratio"] or 1.0),
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
                    fill_order_json, strategy_name, selection_strategy, enabled_item_ids_json,
                    tail_diff_threshold, fallback_l3_item_id, max_simulation_ratio,
                    current_version, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(template_name)
                DO UPDATE SET
                    ratios_json = excluded.ratios_json,
                    l4_max_ratio = excluded.l4_max_ratio,
                    ratio_warning_threshold = excluded.ratio_warning_threshold,
                    fill_order_json = excluded.fill_order_json,
                    strategy_name = excluded.strategy_name,
                    selection_strategy = excluded.selection_strategy,
                    enabled_item_ids_json = excluded.enabled_item_ids_json,
                    tail_diff_threshold = excluded.tail_diff_threshold,
                    fallback_l3_item_id = excluded.fallback_l3_item_id,
                    max_simulation_ratio = excluded.max_simulation_ratio,
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
                    data["selection_strategy"],
                    json.dumps(data["enabled_item_ids"], ensure_ascii=False),
                    data["tail_diff_threshold"],
                    data["fallback_l3_item_id"],
                    data["max_simulation_ratio"],
                    next_version,
                    created_at,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO allocation_rule_versions (
                    template_name, version, ratios_json, l4_max_ratio,
                    ratio_warning_threshold, fill_order_json, strategy_name,
                    selection_strategy, enabled_item_ids_json, tail_diff_threshold,
                    fallback_l3_item_id, max_simulation_ratio, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["template_name"],
                    next_version,
                    json.dumps(data["ratios"], ensure_ascii=False),
                    data["l4_max_ratio"],
                    data["ratio_warning_threshold"],
                    json.dumps(data["fill_order"], ensure_ascii=False),
                    data["strategy_name"],
                    data["selection_strategy"],
                    json.dumps(data["enabled_item_ids"], ensure_ascii=False),
                    data["tail_diff_threshold"],
                    data["fallback_l3_item_id"],
                    data["max_simulation_ratio"],
                    now,
                ),
            )
            conn.commit()

        return self.get_allocation_rule(template_name=data["template_name"])


config_store = ConfigStore()
