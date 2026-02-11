import math
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from backend.config_store import config_store
from backend.models import BillingItem, Statement, StatementItem, StatementSummary

CONFIG_PATH = Path(__file__).resolve().parent / "data" / "config.xlsx"
LEVELS = ["L1", "L2", "L3", "L4"]
DEFAULT_RATIOS = {"L1": 0.55, "L2": 0.30, "L3": 0.10, "L4": 0.05}
DEFAULT_FILL_ORDER = ["L2", "L3", "L4"]
DEFAULT_STRATEGY = "equal_split_v1"


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


def get_allocation_strategies() -> List[Dict[str, str]]:
    return config_store.list_allocation_strategies()


def load_config() -> List[BillingItem]:
    # Prefer runtime-configurable store. Fallback to Excel for compatibility.
    db_items = config_store.list_billing_items(include_inactive=False)
    if db_items:
        return [
            BillingItem(
                level=str(i["level"]),
                name=str(i["name"]),
                unit=str(i["unit"]),
                price=float(i["price"]),
                is_existing=bool(i["is_existing"]),
                can_simulate=bool(i["can_simulate"]),
                must_use=bool(i["must_use"]),
                category=str(i.get("category", "")),
                billing_note=str(i.get("billing_note", "")),
            )
            for i in db_items
        ]

    excel_items = load_config_seed_payload()
    return [
        BillingItem(
            level=i["level"],
            name=i["name"],
            unit=i["unit"],
            price=i["price"],
            is_existing=i["is_existing"],
            can_simulate=i["can_simulate"],
            must_use=i["must_use"],
            category=i.get("category", ""),
            billing_note=i.get("billing_note", ""),
        )
        for i in excel_items
    ]


def load_config_seed_payload() -> List[Dict]:
    try:
        df = pd.read_excel(CONFIG_PATH)
        items = []
        for _, row in df.iterrows():
            # Parse row
            level = str(row.get("收费层级", "")).strip()

            # Helper to handle nan
            def get_val(val, default=""):
                s = str(val)
                return default if s == "nan" else s

            name = get_val(row.get("收费项")).strip()
            if not name:
                continue  # Skip empty rows

            unit = get_val(row.get("计量单位")).strip()
            category = get_val(row.get("Unnamed: 1")).strip()
            billing_note = get_val(row.get("收费原因/审计解释")).strip()
            raw_price = row.get("建议单价(元)", 0)
            try:
                price = float(raw_price)
                if pd.isna(price):
                    price = 0.0
            except Exception:
                price = 0.0

            is_existing = get_val(row.get("是否来自现有业务")) == "是"
            req = get_val(row.get("制作对账单要求"))
            can_simulate = "模拟" in req or "根据业务数量实际去计算" in req

            must_use = get_val(row.get("计算是否必须使用")) == "必须"

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
                    "allow_discount": False,
                    "status": "ACTIVE",
                    "billing_note": billing_note,
                }
            )

        # Forward fill levels
        current_level = ""
        for item in items:
            if item["level"]:
                current_level = item["level"]
            else:
                item["level"] = current_level

        # Clean up level names (e.g. "系统收费层" -> "L1")
        for item in items:
            item["level"] = _normalize_level(str(item["level"]))

        return items
    except Exception as e:
        print(f"Error loading config: {e}")
        return []


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

    try:
        df = pd.read_excel(file_path)
        rows_total = len(df.index)
        filters = _parse_period_filters(period)
        used_df = df.copy()

        if "年份" in used_df.columns and filters["year"] is not None:
            used_df = used_df[pd.to_numeric(used_df["年份"], errors="coerce") == filters["year"]]

        if "月份" in used_df.columns:
            if filters["month"] is not None:
                used_df = used_df[pd.to_numeric(used_df["月份"], errors="coerce") == filters["month"]]
            elif filters["quarter"] is not None:
                months = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}.get(filters["quarter"], [])
                used_df = used_df[pd.to_numeric(used_df["月份"], errors="coerce").isin(months)]

        if config_items is None:
            config_items = load_config()
        valid_names = {i.name for i in config_items}

        quantities: Dict[str, float] = {}
        matched_columns: List[str] = []
        unmatched_columns: List[str] = []

        normalized_mapping = {}
        for src, target in (column_mapping or {}).items():
            s = str(src).strip()
            t = str(target).strip()
            if s and t:
                normalized_mapping[s] = t

        for col in used_df.columns:
            if col in ["年份", "月份", "服务提供方"]:
                continue

            numeric_col = pd.to_numeric(used_df[col], errors="coerce")
            total = float(numeric_col.sum(skipna=True))
            mapped_target = normalized_mapping.get(str(col).strip())
            target_name = mapped_target if mapped_target else str(col)

            if target_name in valid_names:
                matched_columns.append(f"{col}->{target_name}" if mapped_target else str(col))
                if total > 0:
                    quantities[target_name] = quantities.get(target_name, 0.0) + total
            else:
                # 仅记录有值的非匹配列，避免把空白模板列都算噪音
                if total > 0:
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


def _normalize_ratios(raw_ratios: Optional[Dict[str, float]]) -> Dict[str, float]:
    candidate = raw_ratios or DEFAULT_RATIOS
    cleaned: Dict[str, float] = {}
    for level in LEVELS:
        try:
            cleaned[level] = float(candidate.get(level, 0))
        except Exception:
            cleaned[level] = 0.0

    ratio_sum = sum(cleaned.values())
    if ratio_sum <= 0:
        return dict(DEFAULT_RATIOS)
    return {k: cleaned[k] / ratio_sum for k in LEVELS}


def _normalize_fill_order(raw_fill_order: Optional[List[str]]) -> List[str]:
    fill_order: List[str] = []
    for value in raw_fill_order or []:
        level = str(value).strip().upper()
        if level in LEVELS and level not in fill_order:
            fill_order.append(level)
    if not fill_order:
        return list(DEFAULT_FILL_ORDER)
    return fill_order


def resolve_allocation_rule(rule_template_name: str = "standard", ratios: Optional[Dict[str, float]] = None) -> Dict[str, object]:
    stored_rule = config_store.get_allocation_rule(template_name=rule_template_name or "standard")
    normalized_ratios = _normalize_ratios(ratios if ratios else stored_rule.get("ratios"))
    strategy_name = str(stored_rule.get("strategy_name") or DEFAULT_STRATEGY)
    known_strategies = {s["key"] for s in get_allocation_strategies()}
    if strategy_name not in known_strategies:
        strategy_name = DEFAULT_STRATEGY

    return {
        "template_name": str(stored_rule.get("template_name") or "standard"),
        "version": int(stored_rule.get("version") or 1),
        "strategy_name": strategy_name,
        "ratios": normalized_ratios,
        "l4_max_ratio": float(stored_rule.get("l4_max_ratio", 0.05)),
        "ratio_warning_threshold": float(stored_rule.get("ratio_warning_threshold", 0.15)),
        "fill_order": _normalize_fill_order(stored_rule.get("fill_order")),
    }


def _process_l1_fixed(items_by_level, real_data, upsert_item, warnings, statement_items):
    """处理L1层，业务数据原样写入，数量不变"""
    l1_total = 0.0
    
    for item in items_by_level["L1"]:
        if item.name in real_data and item.price > 0:
            qty = real_data[item.name]
            upsert_item("L1", item, qty, "业务真实数据")
            l1_total += qty * item.price
    
    for item in items_by_level["L1"]:
        if any(i.name == item.name for i in statement_items):
            continue
        if item.must_use:
            upsert_item("L1", item, 1.0, "系统固定")
            l1_total += item.price
    
    return l1_total


def _allocate_integer_floor(level, desired_amount, candidates, upsert_item, warnings):
    """使用floor向下取整分配，返回实际分配金额"""
    if desired_amount <= 0 or not candidates:
        return 0.0
    
    per_item = desired_amount / len(candidates)
    actual_total = 0.0
    
    for idx, item in enumerate(candidates):
        if idx == len(candidates) - 1:
            target = max(desired_amount - actual_total, 0)
        else:
            target = per_item
        
        if target <= 0:
            continue
        
        qty = math.floor(target / item.price)
        if qty > 0:
            amount = qty * item.price
            upsert_item(level, item, qty, "规则分配")
            actual_total += amount
    
    return actual_total


def _try_borrow_from_level(level, need_amount, items_by_level, statement_items):
    """尝试从指定层借调数量释放金额，返回实际释放金额"""
    level_items = [i for i in statement_items if i.level == level]
    
    for existing in level_items:
        config = next((i for i in items_by_level[level] 
                      if i.name == existing.name), None)
        if not config or config.price <= 0:
            continue
        
        price = config.price
        qty_to_reduce = math.ceil(need_amount / price)
        
        if existing.quantity >= qty_to_reduce:
            existing.quantity -= qty_to_reduce
            existing.amount -= qty_to_reduce * price
            return qty_to_reduce * price
    
    return 0


def _handle_positive_diff(diff, items_by_level, statement_items, upsert_item, warnings):
    """处理正差额：优先加L4，不够则从L2/L3借调"""
    epsilon = 0.001
    
    if diff < epsilon:
        return True
    
    l4_candidates = [i for i in items_by_level["L4"] 
                     if i.can_simulate and i.price > 0]
    
    if not l4_candidates:
        warnings.append("L4无可用项目")
        return False
    
    l4_item = l4_candidates[0]
    l4_price = l4_item.price
    
    # 尝试直接添加
    qty = math.floor(diff / l4_price)
    if qty >= 1:
        upsert_item("L4", l4_item, qty, "差额补齐")
        remainder = diff - qty * l4_price
        if remainder > epsilon:
            upsert_item("L4", l4_item, 1, "差额补齐")
        return True
    
    # L4单价>diff，需要借调
    need_amount = l4_price - diff
    
    # 尝试从L2借调
    borrowed = _try_borrow_from_level("L2", need_amount, items_by_level, statement_items)
    if borrowed == 0:
        borrowed = _try_borrow_from_level("L3", need_amount, items_by_level, statement_items)
    
    if borrowed > 0:
        new_diff = diff + borrowed
        qty = math.floor(new_diff / l4_price)
        if qty >= 1:
            upsert_item("L4", l4_item, qty, "差额补齐(借调)")
            return True
    
    return False


def _handle_negative_diff(excess, items_by_level, statement_items, upsert_item, warnings):
    """处理负差额：按L2→L3→L4顺序扣除"""
    epsilon = 0.001
    remaining = excess
    
    for level in ["L2", "L3", "L4"]:
        if remaining < epsilon:
            break
        
        level_items = [i for i in statement_items if i.level == level]
        for existing in level_items:
            if remaining < epsilon:
                break
            
            config = next((i for i in items_by_level[level]
                          if i.name == existing.name), None)
            if not config or config.price <= 0:
                continue
            
            price = config.price
            max_deduct = math.floor(remaining / price)
            actual_deduct = min(max_deduct, int(existing.quantity))
            
            if actual_deduct > 0:
                existing.quantity -= actual_deduct
                existing.amount -= actual_deduct * price
                remaining -= actual_deduct * price
    
    return remaining < epsilon


def _force_final_adjustment(target_amount, statement_items, items_by_level, upsert_item):
    """强制调整确保1:1，优先L4，其次L3"""
    epsilon = 0.001
    current_total = sum(i.amount for i in statement_items)
    diff = target_amount - current_total
    
    if abs(diff) < epsilon:
        return
    
    # 优先调整L4
    for level in ["L4", "L3"]:
        level_items = [i for i in statement_items if i.level == level]
        if not level_items:
            continue
        
        # 获取配置中的价格
        item_config = next((i for i in items_by_level[level] 
                           if i.name == level_items[0].name), None)
        if not item_config:
            continue
            
        item = item_config
        
        if diff > 0:
            # 需要增加
            upsert_item(level, item, 1, "强制调整")
        else:
            # 需要减少
            existing = level_items[0]
            if existing.quantity >= 1:
                existing.quantity -= 1
                existing.amount -= item.price
                if existing.quantity <= 0:
                    statement_items.remove(existing)
        
        new_total = sum(i.amount for i in statement_items)
        if abs(target_amount - new_total) < epsilon:
            return
        
        # 更新diff继续尝试
        diff = target_amount - new_total
    
    # 如果还无法平衡，尝试再加/减一次
    final_total = sum(i.amount for i in statement_items)
    final_diff = target_amount - final_total
    
    if abs(final_diff) > epsilon:
        raise ValueError(f"无法强制调整到目标金额，差异: {final_diff:.2f}")


def _balance_statement(target_amount, items_by_level, statement_items, 
                       upsert_item, warnings):
    """循环平衡直到1:1匹配（最多5次）"""
    epsilon = 0.001
    max_iterations = 5
    
    for iteration in range(max_iterations):
        # 清理空项目
        statement_items[:] = [i for i in statement_items if i.quantity > 0]
        
        current_total = sum(i.amount for i in statement_items)
        diff = target_amount - current_total
        
        if abs(diff) <= epsilon:
            return True, current_total
        
        if diff > 0:
            success = _handle_positive_diff(diff, items_by_level, 
                                           statement_items, upsert_item, warnings)
        else:
            success = _handle_negative_diff(-diff, items_by_level,
                                           statement_items, upsert_item, warnings)
        
        if not success:
            # 强制最终调整
            _force_final_adjustment(target_amount, statement_items, 
                                   items_by_level, upsert_item)
            break
    
    # 最终计算
    actual_total = sum(i.amount for i in statement_items)
    final_diff = target_amount - actual_total
    
    if abs(final_diff) > epsilon:
        raise ValueError(f"无法精确匹配，差异: {final_diff:.2f}")
    
    return True, actual_total


def generate_smart_statement(
    target_amount: float,
    customer: str,
    period: str,
    ratios: Optional[Dict[str, float]] = None,
    business_data_file: Optional[str] = None,
    column_mapping: Optional[Dict[str, str]] = None,
    rule_template_name: str = "standard",
) -> Statement:
    """生成对账单，确保严格1:1金额匹配，数量必须为整数"""
    resolved_rule = resolve_allocation_rule(rule_template_name=rule_template_name, ratios=ratios)
    normalized_ratios = resolved_rule["ratios"]
    l4_max_ratio = float(resolved_rule["l4_max_ratio"])
    ratio_warning_threshold = float(resolved_rule["ratio_warning_threshold"])

    all_items = load_config()
    statement_items: List[StatementItem] = []
    warnings: List[str] = []

    # Load business data if provided
    real_data = {}
    if business_data_file:
        real_data = parse_business_data(
            file_path=business_data_file,
            period=period,
            column_mapping=column_mapping,
        )

    def upsert_item(level: str, item: BillingItem, qty: float, source: str):
        """添加或更新计费项，qty必须为整数"""
        if qty <= 0 or item.price <= 0:
            return
        # 确保数量为整数
        qty = math.floor(qty)
        if qty <= 0:
            return
        amount = qty * item.price
        existing = next((i for i in statement_items if i.level == level and i.name == item.name and i.source == source), None)
        if existing:
            existing.quantity = int(existing.quantity) + qty
            existing.amount = existing.quantity * item.price
        else:
            statement_items.append(
                StatementItem(
                    level=level,
                    name=item.name,
                    unit=item.unit,
                    price=item.price,
                    quantity=qty,
                    amount=amount,
                    source=source,
                )
            )

    # Organize items by level
    items_by_level = {"L1": [], "L2": [], "L3": [], "L4": []}
    for item in all_items:
        if item.level in items_by_level:
            items_by_level[item.level].append(item)
    for level in items_by_level:
        items_by_level[level] = sorted(items_by_level[level], key=lambda x: x.name)

    # Phase 1: L1层固定处理（业务数据原样写入，数量不变）
    _process_l1_fixed(items_by_level, real_data, upsert_item, warnings, statement_items)

    # Phase 2: 计算L2/L3/L4的目标金额
    desired_level_amounts = {level: target_amount * normalized_ratios.get(level, 0.0) for level in LEVELS}
    desired_level_amounts["L4"] = min(desired_level_amounts["L4"], target_amount * l4_max_ratio)

    # Phase 3: L2/L3/L4初始分配（floor向下取整）
    for level in ["L2", "L3", "L4"]:
        candidates = [i for i in items_by_level[level] if i.can_simulate and i.price > 0]
        _allocate_integer_floor(level, desired_level_amounts[level], candidates, upsert_item, warnings)

    # Phase 4: 平衡直到1:1匹配
    success, actual_total = _balance_statement(
        target_amount, items_by_level, statement_items, upsert_item, warnings
    )
    
    if not success:
        raise ValueError("无法生成精确匹配的对账单")

    # Calculate Summary and Validate
    layers_summary = {}
    for level in LEVELS:
        lvl_amt = sum(i.amount for i in statement_items if i.level == level)
        ratio = lvl_amt / target_amount if target_amount > 0 else 0
        layers_summary[level] = {
            "amount": round(lvl_amt, 2),
            "ratio": round(ratio, 4),
        }

        # Validation
        target_ratio = normalized_ratios.get(level, 0)

        if level == "L4" and ratio > l4_max_ratio:
            warnings.append(f"L4 占比 {ratio*100:.2f}% 超过 {l4_max_ratio*100:.2f}% 上限")

        if abs(ratio - target_ratio) > ratio_warning_threshold:
            warnings.append(f"{level} 占比 {ratio*100:.2f}% 严重偏离目标 {target_ratio*100:.2f}%")

    # 严格1:1匹配，diff强制为0
    return Statement(
        customer=customer,
        period=period,
        target_amount=target_amount,
        summary=StatementSummary(
            target_amount=target_amount,
            generated_amount=actual_total,
            diff=0.0,
            layers=layers_summary,
            warnings=warnings,
        ),
        items=statement_items,
    )
