import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    from .config_store import config_store
    from .models import BillingItem, Statement, StatementItem, StatementSummary
except ImportError:
    from config_store import config_store
    from models import BillingItem, Statement, StatementItem, StatementSummary

CONFIG_PATH = Path(__file__).resolve().parent / "data" / "config.xlsx"
LEVELS = ["L1", "L2", "L3", "L4"]
DEFAULT_RATIOS = {"L1": 0.55, "L2": 0.30, "L3": 0.10, "L4": 0.05}
DEFAULT_FILL_ORDER = ["L2", "L3", "L4"]
DEFAULT_STRATEGY = "equal_split_v1"
DEFAULT_SELECTION_STRATEGY = "priority_greedy_v1"


def _normalize_level(raw_level: str) -> str:
    if "系统" in raw_level:
        return "L1"
    if "报告" in raw_level or "L2" in raw_level:
        return "L2"
    if "增值" in raw_level:
        return "L3"
    if "其他" in raw_level:
        return "L4"
    return raw_level


def _normalize_quantity_mode(raw_mode: str, can_simulate: bool = False) -> str:
    """将计费模式标准化为英文（用于内部计算）"""
    mode = str(raw_mode or "").strip()
    
    # 支持中文模式名称
    mode_mapping = {
        "固定入账": "ACTUAL_FULL",
        "智能择取": "ACTUAL_SELECTABLE",
        "模拟填充": "SIMULATED",
        # 兼容英文
        "ACTUAL_FULL": "ACTUAL_FULL",
        "ACTUAL_SELECTABLE": "ACTUAL_SELECTABLE",
        "SIMULATED": "SIMULATED",
        "MANUAL": "MANUAL",
    }
    
    normalized = mode_mapping.get(mode)
    if normalized:
        return normalized
    
    # 默认 fallback
    return "SIMULATED" if can_simulate else "ACTUAL_FULL"


def _resolve_runtime_quantity_mode(raw_quantity_mode: str, raw_billing_mode: str, can_simulate: bool = False) -> str:
    """Runtime mode resolution priority: quantity_mode > billing_mode > legacy fallback."""
    known_aliases = {
        "ACTUAL_FULL",
        "ACTUAL_SELECTABLE",
        "SIMULATED",
        "MANUAL",
        "固定入账",
        "智能择取",
        "模拟填充",
    }
    q_raw = str(raw_quantity_mode or "").strip()
    if q_raw in known_aliases:
        return _normalize_quantity_mode(q_raw, can_simulate=can_simulate)

    b_raw = str(raw_billing_mode or "").strip()
    if b_raw in known_aliases:
        return _normalize_quantity_mode(b_raw, can_simulate=can_simulate)

    return "SIMULATED" if can_simulate else "ACTUAL_FULL"


def _safe_float(v, default: float = 0.0) -> float:
    try:
        fv = float(v)
        if math.isnan(fv):
            return default
        return fv
    except Exception:
        return default


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _normalize_ratio_range(min_ratio: float, max_ratio: float) -> Tuple[float, float]:
    mn = max(0.0, min(_safe_float(min_ratio, 0.0), 1.0))
    mx = max(0.0, min(_safe_float(max_ratio, 1.0), 1.0))
    if mn > mx:
        mn, mx = mx, mn
    return mn, mx


def _normalize_qty(raw_qty: float, allow_decimal: bool = False) -> float:
    qty = _safe_float(raw_qty, 0.0)
    if allow_decimal:
        return max(qty, 0.0)
    return float(max(math.floor(qty), 0))


def get_allocation_strategies() -> List[Dict[str, str]]:
    return config_store.list_allocation_strategies()


def load_config() -> List[BillingItem]:
    db_items = config_store.list_billing_items(include_inactive=False)
    if db_items:
        parsed: List[BillingItem] = []
        for i in db_items:
            # Runtime uses quantity_mode first; billing_mode is for UI/editor semantics.
            billing_mode = i.get("billing_mode", "智能择取")
            quantity_mode = _resolve_runtime_quantity_mode(
                raw_quantity_mode=i.get("quantity_mode", ""),
                raw_billing_mode=billing_mode,
                can_simulate=bool(i.get("can_simulate", False)),
            )
            
            # V2.0: 优先级默认值按层级
            level = str(i.get("level", "L3"))
            default_priority = {"L1": 10, "L2": 50, "L3": 100, "L4": 200}.get(level, 100)
            pick_priority = _safe_int(i.get("pick_priority"), default_priority)
            
            # V2.0: require_business_data 默认为 True
            require_business_data = bool(i.get("require_business_data", True))
            
            parsed.append(
                BillingItem(
                    id=_safe_int(i.get("id"), 0) or None,
                    level=level,
                    name=str(i["name"]),
                    unit=str(i["unit"]),
                    price=_safe_float(i.get("price"), 0.0),
                    billing_mode=billing_mode,
                    pick_priority=pick_priority,
                    require_business_data=require_business_data,
                    # 兼容旧字段
                    is_existing=bool(i.get("is_existing", False)),
                    can_simulate=bool(i.get("can_simulate", False)),
                    must_use=bool(i.get("must_use", False)),
                    is_enabled_default=bool(i.get("is_enabled_default", True)),
                    quantity_mode=quantity_mode,
                    min_pick_ratio=_safe_float(i.get("min_pick_ratio"), 0.0),
                    max_pick_ratio=_safe_float(i.get("max_pick_ratio"), 1.0),
                    report_required=bool(i.get("report_required", False)),
                    tail_balance_eligible=bool(i.get("tail_balance_eligible", False)),
                    category=str(i.get("category", "")),
                    billing_note=str(i.get("billing_note", "")),
                    status=str(i.get("status", "启用")),
                )
            )
        return parsed

    excel_items = load_config_seed_payload()
    return [BillingItem(**i) for i in excel_items]


def load_config_seed_payload() -> List[Dict]:
    # 定义默认的回退数据，以防配置文件丢失
    fallback_items = [
        {"level": "L1", "name": "租户基础服务费", "unit": "元/月", "price": 2000.0, "quantity_mode": "ACTUAL_FULL", "must_use": True, "category": "基础服务"},
        {"level": "L1", "name": "API调用服务包", "unit": "千次", "price": 50.0, "quantity_mode": "ACTUAL_SELECTABLE", "can_simulate": False, "category": "增值服务"},
        {"level": "L1", "name": "数据存储扩容", "unit": "GB/月", "price": 1.0, "quantity_mode": "ACTUAL_SELECTABLE", "can_simulate": False, "category": "增值服务"},
        
        {"level": "L2", "name": "标准报告生成费", "unit": "份", "price": 50.0, "quantity_mode": "SIMULATED", "can_simulate": True, "category": "报告服务"},
        {"level": "L2", "name": "定制化报表开发", "unit": "人天", "price": 3000.0, "quantity_mode": "SIMULATED", "can_simulate": True, "category": "报告服务"},
        
        {"level": "L3", "name": "增值服务费", "unit": "次", "price": 100.0, "quantity_mode": "SIMULATED", "can_simulate": True, "category": "咨询服务"},
        {"level": "L3", "name": "专家咨询工时", "unit": "小时", "price": 800.0, "quantity_mode": "SIMULATED", "can_simulate": True, "category": "咨询服务"},
        
        {"level": "L4", "name": "其他费用", "unit": "项", "price": 10.0, "quantity_mode": "SIMULATED", "can_simulate": True, "tail_balance_eligible": True, "category": "其他"},
        {"level": "L4", "name": "零星调整", "unit": "元", "price": 1.0, "quantity_mode": "SIMULATED", "can_simulate": True, "tail_balance_eligible": True, "category": "其他"},
    ]

    try:
        if not CONFIG_PATH.exists():
            print(f"Config file not found at: {CONFIG_PATH}. Using fallback items.")
            return fallback_items
            
        df = pd.read_excel(CONFIG_PATH)
    except Exception as e:
        print(f"Error loading config: {e}. Using fallback items.")
        return fallback_items

    items = []
    for _, row in df.iterrows():
        def get_val(val, default=""):
            s = str(val)
            return default if s == "nan" else s

        level = get_val(row.get("收费层级", "")).strip()
        name = get_val(row.get("收费项")).strip()
        if not name:
            continue

        unit = get_val(row.get("计量单位")).strip()
        category = get_val(row.get("Unnamed: 1")).strip()
        billing_note = get_val(row.get("收费原因/审计解释")).strip()
        price = _safe_float(row.get("建议单价(元)", 0), 0.0)
        is_existing = get_val(row.get("是否来自现有业务")) == "是"
        req = get_val(row.get("制作对账单要求"))
        can_simulate = "模拟" in req
        must_use = get_val(row.get("计算是否必须使用")) == "必须"
        quantity_mode = "SIMULATED" if can_simulate else "ACTUAL_FULL"
        if "根据业务数量实际去计算" in req:
            quantity_mode = "ACTUAL_SELECTABLE"

        items.append(
            {
                "code": None,
                "level": level if level != "nan" else "",
                "name": name,
                "category": category,
                "unit": unit,
                "price": price,
                "is_existing": is_existing,
                "can_simulate": can_simulate,
                "must_use": must_use,
                "is_enabled_default": True,
                "quantity_mode": quantity_mode,
                "min_pick_ratio": 0.0,
                "max_pick_ratio": 1.0,
                "pick_priority": 100,
                "report_required": ("报告" in name),
                "tail_balance_eligible": ("L4" in level or "其他" in level),
                "allow_discount": False,
                "status": "ACTIVE",
                "billing_note": billing_note,
            }
        )

    current_level = ""
    for item in items:
        if item["level"]:
            current_level = item["level"]
        else:
            item["level"] = current_level
        item["level"] = _normalize_level(str(item["level"]))
        if item["level"] == "L4":
            item["tail_balance_eligible"] = True

    return items


def _parse_period_filters(period: Optional[str]) -> Dict[str, Optional[int]]:
    if not period:
        return {"year": None, "month": None, "quarter": None}
    p = str(period).strip().upper()
    if "-Q" in p:
        try:
            year, q = p.split("-Q")
            return {"year": int(year), "month": None, "quarter": int(q)}
        except Exception:
            return {"year": None, "month": None, "quarter": None}
    if "-" in p:
        try:
            year, month = p.split("-")
            return {"year": int(year), "month": int(month), "quarter": None}
        except Exception:
            return {"year": None, "month": None, "quarter": None}
    if len(p) == 4 and p.isdigit():
        return {"year": int(p), "month": None, "quarter": None}
    return {"year": None, "month": None, "quarter": None}


def _read_business_columns(file_path: str) -> List[str]:
    ext = Path(file_path).suffix.lower()
    if ext in [".csv", ".txt"]:
        try:
            return list(pd.read_csv(file_path, nrows=0).columns)
        except Exception:
            return []
    try:
        try:
            return list(pd.read_excel(file_path, engine="calamine", nrows=0).columns)
        except Exception:
            return list(pd.read_excel(file_path, nrows=0).columns)
    except Exception:
        return []


def _read_business_dataframe(file_path: str, usecols: Optional[List[str]]) -> pd.DataFrame:
    ext = Path(file_path).suffix.lower()
    if ext in [".csv", ".txt"]:
        return pd.read_csv(file_path, usecols=usecols)
    try:
        try:
            return pd.read_excel(file_path, engine="calamine", usecols=usecols)
        except Exception:
            return pd.read_excel(file_path, usecols=usecols)
    except Exception:
        return pd.DataFrame()


def parse_business_data_preview(
    file_path: str,
    period: Optional[str],
    config_items: Optional[List[BillingItem]] = None,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Dict:
    if not file_path or not os.path.exists(file_path):
        return {
            "period": period or "",
            "filters": _parse_period_filters(period),
            "rows_total": 0,
            "rows_used": 0,
            "matched_columns": [],
            "unmatched_columns": [],
            "quantities": {},
        }

    if config_items is None:
        config_items = load_config()
    valid_names = {i.name for i in config_items}

    normalized_mapping: Dict[str, str] = {}
    for src, target in (column_mapping or {}).items():
        s = str(src).strip()
        t = str(target).strip()
        if s and t:
            normalized_mapping[s] = t

    available_columns = _read_business_columns(file_path)
    preferred_cols = {"年份", "月份", "服务提供方"}
    preferred_cols.update(normalized_mapping.keys())
    preferred_cols.update(valid_names)
    usecols = [c for c in available_columns if c in preferred_cols]
    if not usecols:
        usecols = None

    try:
        df = _read_business_dataframe(file_path, usecols=usecols)
    except Exception as e:
        print(f"Error parsing business data preview: {e}")
        return {
            "period": period or "",
            "filters": _parse_period_filters(period),
            "rows_total": 0,
            "rows_used": 0,
            "matched_columns": [],
            "unmatched_columns": [],
            "quantities": {},
        }

    rows_total = len(df.index)
    filters = _parse_period_filters(period)
    used_df = df
    if "年份" in used_df.columns and filters["year"] is not None:
        used_df = used_df[pd.to_numeric(used_df["年份"], errors="coerce") == filters["year"]]
    if "月份" in used_df.columns:
        if filters["month"] is not None:
            used_df = used_df[pd.to_numeric(used_df["月份"], errors="coerce") == filters["month"]]
        elif filters["quarter"] is not None:
            months = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}.get(filters["quarter"], [])
            used_df = used_df[pd.to_numeric(used_df["月份"], errors="coerce").isin(months)]

    quantities: Dict[str, float] = {}
    matched_columns: List[str] = []
    unmatched_columns: List[str] = []
    for col in used_df.columns:
        if col in ["年份", "月份", "服务提供方"]:
            continue
        total = _safe_float(pd.to_numeric(used_df[col], errors="coerce").sum(skipna=True), 0.0)
        mapped_target = normalized_mapping.get(str(col).strip())
        target_name = mapped_target if mapped_target else str(col)
        if target_name in valid_names:
            matched_columns.append(f"{col}->{target_name}" if mapped_target else str(col))
            if total > 0:
                quantities[target_name] = quantities.get(target_name, 0.0) + total
        elif total > 0:
            unmatched_columns.append(str(col))

    return {
        "period": period or "",
        "filters": filters,
        "rows_total": rows_total,
        "rows_used": len(used_df.index),
        "matched_columns": sorted(matched_columns),
        "unmatched_columns": sorted(unmatched_columns),
        "quantities": quantities,
    }


def parse_business_data(
    file_path: str,
    period: Optional[str] = None,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, float]:
    parsed = parse_business_data_preview(
        file_path=file_path,
        period=period,
        config_items=load_config(),
        column_mapping=column_mapping,
    )
    return parsed["quantities"]


def _normalize_ratios(raw_ratios: Optional[Dict[str, float]]) -> Dict[str, float]:
    candidate = raw_ratios or DEFAULT_RATIOS
    cleaned = {level: max(_safe_float(candidate.get(level, 0.0), 0.0), 0.0) for level in LEVELS}
    total = sum(cleaned.values())
    if total <= 0:
        return dict(DEFAULT_RATIOS)
    return {level: cleaned[level] / total for level in LEVELS}


def _normalize_fill_order(raw_fill_order: Optional[List[str]]) -> List[str]:
    fill_order: List[str] = []
    for value in raw_fill_order or []:
        level = str(value).strip().upper()
        if level in LEVELS and level not in fill_order:
            fill_order.append(level)
    return fill_order or list(DEFAULT_FILL_ORDER)


def resolve_allocation_rule(rule_template_name: str = "standard", ratios: Optional[Dict[str, float]] = None) -> Dict[str, object]:
    stored_rule = config_store.get_allocation_rule(template_name=rule_template_name or "standard")
    strategy_name = str(stored_rule.get("strategy_name") or DEFAULT_STRATEGY)
    selection_strategy = str(stored_rule.get("selection_strategy") or DEFAULT_SELECTION_STRATEGY)
    known = {s["key"] for s in get_allocation_strategies()}
    if strategy_name not in known:
        strategy_name = DEFAULT_STRATEGY
    if selection_strategy not in known:
        selection_strategy = DEFAULT_SELECTION_STRATEGY

    return {
        "template_name": str(stored_rule.get("template_name") or "standard"),
        "version": int(stored_rule.get("version") or 1),
        "strategy_name": strategy_name,
        "selection_strategy": selection_strategy,
        "ratios": _normalize_ratios(ratios if ratios else stored_rule.get("ratios")),
        "l4_max_ratio": _safe_float(stored_rule.get("l4_max_ratio"), 0.05),
        "ratio_warning_threshold": _safe_float(stored_rule.get("ratio_warning_threshold"), 0.15),
        "fill_order": _normalize_fill_order(stored_rule.get("fill_order")),
        "enabled_item_ids": [int(x) for x in (stored_rule.get("enabled_item_ids") or []) if str(x).isdigit()],
        "tail_diff_threshold": max(_safe_float(stored_rule.get("tail_diff_threshold"), 0.0), 0.0),
        "fallback_l3_item_id": stored_rule.get("fallback_l3_item_id"),
        "max_simulation_ratio": max(0.0, min(_safe_float(stored_rule.get("max_simulation_ratio"), 1.0), 1.0)),
    }


class _SelectableEntry:
    def __init__(self, item: BillingItem, actual_qty: int):
        self.item = item
        self.actual_qty = max(actual_qty, 0)
        mn_ratio, mx_ratio = _normalize_ratio_range(item.min_pick_ratio, item.max_pick_ratio)
        self.min_qty = min(max(int(math.ceil(self.actual_qty * mn_ratio)), 0), self.actual_qty)
        self.max_qty = min(max(int(math.floor(self.actual_qty * mx_ratio)), 0), self.actual_qty)
        if self.max_qty < self.min_qty:
            self.min_qty = self.max_qty
        self.qty = self.min_qty

    @property
    def min_amount(self) -> float:
        return self.min_qty * self.item.price

    @property
    def amount(self) -> float:
        return self.qty * self.item.price

    @property
    def remaining_capacity(self) -> int:
        return max(self.max_qty - self.qty, 0)


def _rank_selectable(entries: List[_SelectableEntry]) -> List[_SelectableEntry]:
    return sorted(entries, key=lambda e: (e.item.pick_priority, -e.item.price, e.item.name))


def _bounded_backtracking(entries: List[_SelectableEntry], target_delta: float) -> float:
    if target_delta <= 0:
        return 0.0
    ranked = _rank_selectable(entries)
    best_remaining = max(target_delta, 0.0)
    best_state = [e.qty for e in ranked]
    max_states = 5000
    seen = {"count": 0}

    def dfs(idx: int, remaining: float):
        if remaining < -1e-9:
            return
        if seen["count"] >= max_states:
            return
        seen["count"] += 1
        nonlocal best_remaining, best_state
        if remaining < best_remaining - 1e-6:
            best_remaining = remaining
            best_state = [e.qty for e in ranked]
            if best_remaining <= 0.01:
                return
        if idx >= len(ranked):
            return
        entry = ranked[idx]
        if entry.item.price <= 0:
            dfs(idx + 1, remaining)
            return
        max_add = entry.remaining_capacity
        if max_add <= 0:
            dfs(idx + 1, remaining)
            return

        # Enforce non-overshoot: selectable phase should not exceed target.
        max_add_by_remaining = int(max(0, math.floor((remaining + 1e-9) / entry.item.price)))
        max_add = min(max_add, max_add_by_remaining)
        if max_add <= 0:
            dfs(idx + 1, remaining)
            return

        approx = int(max(0, min(max_add, math.floor(remaining / entry.item.price))))
        candidates = [approx, max_add, 0, approx - 1, approx + 1, approx - 2, approx + 2]
        tried = set()
        for add in candidates:
            add = max(0, min(max_add, add))
            if add in tried:
                continue
            tried.add(add)
            old = entry.qty
            entry.qty = old + add
            dfs(idx + 1, remaining - add * entry.item.price)
            entry.qty = old
            if best_remaining <= 0.01:
                return

    dfs(0, target_delta)
    for i, qty in enumerate(best_state):
        ranked[i].qty = qty
    return best_remaining


def _select_actual_quantities(entries: List[_SelectableEntry], target_amount: float, warnings: List[str]) -> Tuple[float, bool]:
    if not entries:
        return 0.0, True

    minimum = sum(e.min_amount for e in entries)
    maximum = sum(e.max_qty * e.item.price for e in entries)
    if minimum - target_amount > 0.01:
        warnings.append(
            f"ACTUAL_SELECTABLE 最小可计费金额 {minimum:.2f} 超过目标可分配金额 {target_amount:.2f}。"
        )
        return minimum, False
    if target_amount - maximum > 0.01:
        warnings.append(
            f"ACTUAL_SELECTABLE 最大可计费金额 {maximum:.2f} 低于目标可分配金额 {target_amount:.2f}。"
        )
        # Still return max and let simulated phase handle remaining gap.
    ranked = _rank_selectable(entries)
    current = minimum
    remaining = max(target_amount - current, 0.0)

    while remaining > 0.01:
        fit = [e for e in ranked if e.remaining_capacity > 0 and e.item.price <= remaining + 1e-9]
        if not fit:
            break
        picked = fit[0]
        picked.qty += 1
        current += picked.item.price
        remaining = max(target_amount - current, 0.0)

    if remaining > 0.01:
        _bounded_backtracking(entries=ranked, target_delta=remaining)
        current = sum(e.amount for e in ranked)
    return current, True


def _allocate_simulation(
    remaining_amount: float,
    simulated_items: List[BillingItem],
    fill_order: List[str],
    max_simulation_amount: float,
) -> Tuple[Dict[str, float], float]:
    if remaining_amount <= 0.01 or max_simulation_amount <= 0.01:
        return {}, 0.0

    allocated: Dict[str, float] = {}
    total = 0.0
    ordered_levels = [lv for lv in fill_order if lv in LEVELS and lv != "L4"] + ["L2", "L3"]
    seen_levels = []
    for lv in ordered_levels:
        if lv not in seen_levels:
            seen_levels.append(lv)

    level_buckets: Dict[str, List[BillingItem]] = {lv: [] for lv in LEVELS}
    for item in simulated_items:
        level_buckets[item.level].append(item)
    for lv in level_buckets:
        level_buckets[lv] = sorted(level_buckets[lv], key=lambda x: (x.pick_priority, -x.price, x.name))

    diff = min(remaining_amount, max_simulation_amount)
    for level in seen_levels:
        if diff <= 0.01:
            break
        for item in level_buckets.get(level, []):
            if diff <= 0.01:
                break
            if item.price <= 0:
                continue
            qty = int(math.floor(diff / item.price))
            if qty <= 0:
                continue
            amount = qty * item.price
            allocated[item.name] = allocated.get(item.name, 0.0) + qty
            total += amount
            diff -= amount

    return allocated, total


def _derive_tail_threshold(config_threshold: float, selectable_entries: List[_SelectableEntry], simulated_items: List[BillingItem]) -> float:
    if config_threshold > 0:
        return config_threshold
    prices: List[float] = []
    for entry in selectable_entries:
        if entry.item.price > 0:
            prices.append(entry.item.price)
    for item in simulated_items:
        if item.price > 0 and item.level in {"L2", "L3"}:
            prices.append(item.price)
    if not prices:
        return 0.01
    return min(prices)


def _pick_tail_balance_item(all_items: List[BillingItem]) -> Optional[BillingItem]:
    candidates = [i for i in all_items if i.tail_balance_eligible and i.level == "L4" and i.price > 0]
    if not candidates:
        candidates = [i for i in all_items if i.level == "L4" and i.price > 0]
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: (x.pick_priority, x.price, x.name))[0]


def _build_item(
    item: BillingItem,
    billed_qty: float,
    source: str,
    reason_code: str,
    actual_qty: float,
    allow_decimal: bool = False,
) -> Optional[StatementItem]:
    qty = _normalize_qty(billed_qty, allow_decimal=allow_decimal)
    if qty <= 0 and abs(qty) <= 1e-9:
        return None
    amount = qty * item.price
    actual = _normalize_qty(actual_qty, allow_decimal=False)
    unbilled = max(actual - _normalize_qty(qty, allow_decimal=False), 0.0)
    return StatementItem(
        level=item.level,
        name=item.name,
        unit=item.unit,
        price=item.price,
        quantity=qty,
        amount=amount,
        source=source,
        quantity_mode=item.quantity_mode,
        actual_qty=actual,
        billed_qty=qty,
        unbilled_qty=unbilled if item.quantity_mode == "ACTUAL_SELECTABLE" else 0.0,
        decision_reason_code=reason_code,
        category=item.category,
        billing_note=item.billing_note,
    )


def _classify_generation_error(message: str) -> str:
    msg = str(message or "")
    if "固定费用超过目标金额" in msg:
        return "FIXED_EXCEEDS_TARGET"
    if "ACTUAL_SELECTABLE 约束不可行" in msg:
        return "SELECTABLE_INFEASIBLE"
    if "超过尾差阈值" in msg:
        return "TAIL_DIFF_EXCEEDED"
    if "缺少可用 L4 尾差承接项" in msg:
        return "TAIL_ITEM_MISSING"
    if "策略启用项为空" in msg:
        return "NO_ENABLED_ITEMS"
    return "UNSPECIFIED"


def precheck_statement_feasibility_lightweight(
    target_amount: float,
    business_data_quantities: Optional[Dict[str, float]] = None,
    config_items: Optional[List[BillingItem]] = None,
) -> Dict:
    """
    轻量级可行性检查 - 只验证业务数据总量是否足够
    优点：不执行完整的对账单生成，速度极快
    """
    if business_data_quantities is None:
        business_data_quantities = {}

    if config_items is None:
        config_items = load_config()

    # 计算可用总金额（只考虑需要业务数据的计费项）
    total_available = 0.0
    item_details = []

    for item in config_items:
        if not item.require_business_data or item.price <= 0:
            continue

        qty = business_data_quantities.get(item.name, 0)
        if qty > 0:
            item_total = qty * item.price
            total_available += item_total
            item_details.append({
                "name": item.name,
                "quantity": qty,
                "price": item.price,
                "total": item_total,
            })

    if total_available < target_amount:
        return {
            "feasible": False,
            "reason_code": "INSUFFICIENT_DATA",
            "message": f"业务数据可用金额 ¥{total_available:,.2f} 小于目标金额 ¥{target_amount:,.2f}",
            "total_available": total_available,
            "target_amount": float(target_amount),
            "item_count": len(item_details),
            "items": item_details,
        }

    return {
        "feasible": True,
        "reason_code": "OK",
        "message": "业务数据充足",
        "total_available": total_available,
        "target_amount": float(target_amount),
        "item_count": len(item_details),
        "items": item_details,
    }


def precheck_statement_feasibility(
    target_amount: float,
    customer: str,
    period: str,
    ratios: Optional[Dict[str, float]] = None,
    business_data_file: Optional[str] = None,
    business_data_quantities: Optional[Dict[str, float]] = None,
    column_mapping: Optional[Dict[str, str]] = None,
    rule_template_name: str = "standard",
) -> Dict:
    try:
        stmt = generate_smart_statement(
            target_amount=target_amount,
            customer=customer,
            period=period,
            ratios=ratios,
            business_data_file=business_data_file,
            business_data_quantities=business_data_quantities,
            column_mapping=column_mapping,
            rule_template_name=rule_template_name,
        )
        return {
            "feasible": True,
            "reason_code": "OK",
            "message": "可行",
            "generated_amount": float(stmt.summary.generated_amount),
            "target_amount": float(target_amount),
            "warnings": list(stmt.summary.warnings or []),
            "snapshot": dict(stmt.summary.calc_snapshot_json or {}),
        }
    except Exception as exc:
        msg = str(exc)
        return {
            "feasible": False,
            "reason_code": _classify_generation_error(msg),
            "message": msg,
            "generated_amount": None,
            "target_amount": float(target_amount),
            "warnings": [],
            "snapshot": {},
        }


def generate_smart_statement(
    target_amount: float,
    customer: str,
    period: str,
    ratios: Optional[Dict[str, float]] = None,
    business_data_file: Optional[str] = None,
    business_data_quantities: Optional[Dict[str, float]] = None,
    column_mapping: Optional[Dict[str, str]] = None,
    rule_template_name: str = "standard",
) -> Statement:
    resolved_rule = resolve_allocation_rule(rule_template_name=rule_template_name, ratios=ratios)
    normalized_ratios = resolved_rule["ratios"]
    fill_order = resolved_rule["fill_order"]
    tail_diff_threshold = _safe_float(resolved_rule.get("tail_diff_threshold", 0.0), 0.0)
    max_simulation_ratio = _safe_float(resolved_rule.get("max_simulation_ratio", 1.0), 1.0)
    enabled_item_ids = set(resolved_rule.get("enabled_item_ids") or [])

    all_items = load_config()
    warnings = []
    if enabled_item_ids:
        filtered = [item for item in all_items if item.id is not None and item.id in enabled_item_ids]
        missing_count = len(enabled_item_ids) - len(filtered)
        if missing_count > 0:
            warnings.append(f"策略启用项中有 {missing_count} 个ID未命中有效计费项，已自动忽略。")
        if not filtered:
            raise ValueError("策略启用项为空或无有效ID，无法生成账单。")
        all_items = filtered

    real_data = {}
    if business_data_quantities is not None:
        real_data = dict(business_data_quantities)
    elif business_data_file:
        real_data = parse_business_data(
            file_path=business_data_file,
            period=period,
            column_mapping=column_mapping,
        )
    actual_qty_map = {name: _normalize_qty(q, allow_decimal=False) for name, q in real_data.items()}
    has_report_support = any(("报告" in name and qty > 0) for name, qty in actual_qty_map.items())

    fixed_items: List[StatementItem] = []
    selectable_entries: List[_SelectableEntry] = []
    simulated_items: List[BillingItem] = []
    manual_items: List[BillingItem] = []
    decision_rows: List[Dict] = []
    calc_logs: List[str] = []

    for item in all_items:
        if item.price <= 0:
            continue
        mode = _normalize_quantity_mode(item.quantity_mode, item.can_simulate)
        item.quantity_mode = mode
        actual_qty = int(actual_qty_map.get(item.name, 0))

        if mode == "ACTUAL_FULL":
            billed = actual_qty
            if billed > 0:
                st_item = _build_item(
                    item=item,
                    billed_qty=billed,
                    source="业务真实数据",
                    reason_code="POLICY_FULL_BILLING",
                    actual_qty=actual_qty,
                )
                if st_item:
                    fixed_items.append(st_item)
            decision_rows.append(
                {
                    "item": item.name,
                    "quantity_mode": mode,
                    "actual_qty": actual_qty,
                    "billed_qty": billed,
                    "unbilled_qty": 0,
                    "reason_code": "POLICY_FULL_BILLING",
                }
            )
            continue

        if mode == "ACTUAL_SELECTABLE":
            entry = _SelectableEntry(item=item, actual_qty=actual_qty)
            selectable_entries.append(entry)
            decision_rows.append(
                {
                    "item": item.name,
                    "quantity_mode": mode,
                    "actual_qty": actual_qty,
                    "billed_qty": entry.qty,
                    "unbilled_qty": max(actual_qty - entry.qty, 0),
                    "reason_code": "TARGET_ALIGNMENT",
                }
            )
            continue

        if mode == "SIMULATED":
            simulated_items.append(item)
            decision_rows.append(
                {
                    "item": item.name,
                    "quantity_mode": mode,
                    "actual_qty": actual_qty,
                    "billed_qty": 0,
                    "unbilled_qty": 0,
                    "reason_code": "SIMULATION_FILL_GAP",
                }
            )
            continue

        manual_items.append(item)
        decision_rows.append(
            {
                "item": item.name,
                "quantity_mode": mode,
                "actual_qty": actual_qty,
                "billed_qty": 0,
                "unbilled_qty": 0,
                "reason_code": "MANUAL_REQUIRED",
            }
        )

    fixed_total = sum(i.amount for i in fixed_items)
    if fixed_total - target_amount > 0.01:
        raise ValueError(
            f"固定费用超过目标金额。目标:{target_amount:.2f}，固定金额:{fixed_total:.2f}。"
        )
    calc_logs.append(f"fixed_total={fixed_total:.2f}")

    remaining = target_amount - fixed_total
    selectable_amount, feasible = _select_actual_quantities(selectable_entries, remaining, warnings)
    calc_logs.append(f"selectable_amount={selectable_amount:.2f}, feasible={feasible}")
    if not feasible:
        raise ValueError("ACTUAL_SELECTABLE 约束不可行，请调整 min/max_pick_ratio 或目标金额。")

    selected_items: List[StatementItem] = []
    for entry in selectable_entries:
        if entry.qty <= 0:
            continue
        st_item = _build_item(
            item=entry.item,
            billed_qty=entry.qty,
            source="择取计费",
            reason_code="TARGET_ALIGNMENT",
            actual_qty=entry.actual_qty,
        )
        if st_item:
            selected_items.append(st_item)

    after_selectable = fixed_total + selectable_amount
    remaining_after_selectable = target_amount - after_selectable
    if remaining_after_selectable < -0.01:
        raise ValueError(
            f"择取后金额超过目标，无法继续。目标:{target_amount:.2f}，当前:{after_selectable:.2f}"
        )

    simulation_pool = simulated_items
    no_report_fallback_item: Optional[BillingItem] = None
    if not has_report_support:
        l3_only = [i for i in simulated_items if i.level == "L3"]
        if l3_only:
            simulation_pool = l3_only
            no_report_fallback_item = sorted(l3_only, key=lambda x: (x.price, x.pick_priority, x.name))[0]
            warnings.append("未检测到报告类业务支撑，差额将统一回落至 L3。")
        else:
            warnings.append("未检测到报告类业务支撑，且未找到可用 L3 回落项。")
    max_sim_amount = target_amount * max_simulation_ratio
    if no_report_fallback_item and no_report_fallback_item.price > 0:
        allocatable = min(remaining_after_selectable, max_sim_amount)
        qty = int(math.floor(allocatable / no_report_fallback_item.price))
        sim_qty_map = {no_report_fallback_item.name: float(qty)} if qty > 0 else {}
        simulated_amount = qty * no_report_fallback_item.price
    else:
        sim_qty_map, simulated_amount = _allocate_simulation(
            remaining_amount=remaining_after_selectable,
            simulated_items=simulation_pool,
            fill_order=fill_order,
            max_simulation_amount=max_sim_amount,
        )
    calc_logs.append(f"simulated_amount={simulated_amount:.2f}, max_sim_amount={max_sim_amount:.2f}")
    simulated_statement_items: List[StatementItem] = []
    sim_item_by_name = {i.name: i for i in simulated_items}
    for name, qty in sim_qty_map.items():
        item = sim_item_by_name.get(name)
        if not item:
            continue
        st_item = _build_item(
            item=item,
            billed_qty=qty,
            source="规则分配",
            reason_code="SIMULATION_FILL_GAP",
            actual_qty=actual_qty_map.get(name, 0.0),
        )
        if st_item:
            simulated_statement_items.append(st_item)

    statement_items = fixed_items + selected_items + simulated_statement_items
    current_total = sum(i.amount for i in statement_items)
    diff = target_amount - current_total
    calc_logs.append(f"before_tail_diff={diff:.2f}")
    effective_tail_threshold = _derive_tail_threshold(tail_diff_threshold, selectable_entries, simulation_pool)

    if abs(diff) > 0.01:
        if abs(diff) > effective_tail_threshold + 1e-9:
            raise ValueError(
                f"金额差异 {diff:.2f} 超过尾差阈值 {effective_tail_threshold:.2f}，不允许通过 L4 兜底。"
            )
        tail_item = _pick_tail_balance_item(all_items)
        if not tail_item:
            raise ValueError(
                f"存在尾差 {diff:.2f} 但缺少可用 L4 尾差承接项。"
            )
        tail_qty = diff / tail_item.price
        tail_row = _build_item(
            item=tail_item,
            billed_qty=tail_qty,
            source="尾差调平",
            reason_code="TAIL_BALANCE",
            actual_qty=0.0,
            allow_decimal=True,
        )
        if not tail_row:
            raise ValueError(f"尾差调平失败，差异:{diff:.2f}")
        statement_items.append(tail_row)

    final_total = sum(i.amount for i in statement_items)
    final_diff = target_amount - final_total
    if abs(final_diff) > 0.01:
        raise ValueError(f"最终金额未对齐。目标:{target_amount:.2f}，当前:{final_total:.2f}，差异:{final_diff:.2f}")

    # Update decision rows with final billed/unbilled.
    billed_map = {item.name: item for item in statement_items}
    for row in decision_rows:
        st_item = billed_map.get(row["item"])
        if st_item:
            row["billed_qty"] = st_item.billed_qty
            row["unbilled_qty"] = st_item.unbilled_qty
            row["reason_code"] = st_item.decision_reason_code or row["reason_code"]

    layers_summary = {}
    for level in LEVELS:
        level_amount = sum(i.amount for i in statement_items if i.level == level)
        ratio = (level_amount / target_amount) if target_amount > 0 else 0.0
        layers_summary[level] = {"amount": round(level_amount, 2), "ratio": round(ratio, 4)}
        target_ratio = normalized_ratios.get(level, 0.0)
        if abs(ratio - target_ratio) > _safe_float(resolved_rule.get("ratio_warning_threshold"), 0.15):
            warnings.append(f"{level} 占比 {ratio*100:.2f}% 偏离目标 {target_ratio*100:.2f}%")

    snapshot = {
        "engine_version": "v2",
        "rule_snapshot_version": int(resolved_rule.get("version", 1)),
        "rule_template_name": resolved_rule.get("template_name", rule_template_name),
        "selection_strategy": resolved_rule.get("selection_strategy", DEFAULT_SELECTION_STRATEGY),
        "constraints": {
            "tail_diff_threshold": effective_tail_threshold,
            "max_simulation_ratio": max_simulation_ratio,
            "amount_tolerance": 0.01,
        },
        "input": {
            "target_amount": target_amount,
            "actual_qty_items": len(actual_qty_map),
            "business_data_file": bool(business_data_file),
        },
        "stages": {
            "fixed_total": round(fixed_total, 2),
            "selectable_total": round(selectable_amount, 2),
            "simulated_total": round(simulated_amount, 2),
            "final_total": round(final_total, 2),
            "final_diff": round(final_diff, 4),
        },
        "logs": calc_logs,
    }

    return Statement(
        customer=customer,
        period=period,
        target_amount=target_amount,
        summary=StatementSummary(
            target_amount=target_amount,
            generated_amount=round(final_total, 2),
            diff=round(final_diff, 4),
            layers=layers_summary,
            warnings=warnings,
            calc_snapshot_json=snapshot,
            item_decision_json=decision_rows,
        ),
        items=statement_items,
    )
