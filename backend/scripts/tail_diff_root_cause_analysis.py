#!/usr/bin/env python3
"""
End-to-end root-cause analysis for TAIL_DIFF_EXCEEDED scenarios.

Outputs:
1) analysis/tail_diff_line_recalc.csv
2) analysis/tail_diff_target_scan.csv
3) analysis/tail_diff_summary.txt
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import logic  # noqa: E402


def _read_raw_modes(db_path: Path) -> Dict[str, Dict[str, str]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT name, level, billing_mode, quantity_mode, can_simulate FROM billing_items"
    ).fetchall()
    conn.close()
    return {
        str(r["name"]): {
            "level": str(r["level"]),
            "billing_mode": str(r["billing_mode"]),
            "quantity_mode": str(r["quantity_mode"]),
            "can_simulate": str(r["can_simulate"]),
        }
        for r in rows
    }


def _build_line_recalc(
    business_file: Path,
    period: str,
    output_csv: Path,
) -> Tuple[int, float]:
    df = pd.read_excel(str(business_file))
    config_items = logic.load_config()
    item_map = {i.name: i for i in config_items}
    raw_modes = _read_raw_modes(BACKEND_DIR / "data" / "app.db")

    rows: List[Dict[str, object]] = []
    total_amount = 0.0
    seq = 0
    for row_idx, row in df.iterrows():
        year = int(row.get("年份", 0) or 0)
        month = int(row.get("月份", 0) or 0)
        service_provider = str(row.get("服务提供方", "") or "")
        if period:
            y, m = period.split("-")
            if year != int(y) or month != int(m):
                continue

        for col in df.columns:
            if col in {"年份", "月份", "服务提供方"}:
                continue
            qty = float(pd.to_numeric(row.get(col, 0), errors="coerce") or 0.0)
            item = item_map.get(str(col))
            if item is None:
                continue
            seq += 1
            amount = qty * float(item.price)
            total_amount += amount
            raw = raw_modes.get(item.name, {})
            rows.append(
                {
                    "seq": seq,
                    "source_row": int(row_idx) + 2,
                    "year": year,
                    "month": month,
                    "service_provider": service_provider,
                    "billing_item": item.name,
                    "level": item.level,
                    "qty": qty,
                    "price": float(item.price),
                    "amount": round(amount, 2),
                    "billing_mode_raw": raw.get("billing_mode", ""),
                    "quantity_mode_raw": raw.get("quantity_mode", ""),
                    "runtime_mode": logic._normalize_quantity_mode(item.quantity_mode, item.can_simulate),
                }
            )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seq",
                "source_row",
                "year",
                "month",
                "service_provider",
                "billing_item",
                "level",
                "qty",
                "price",
                "amount",
                "billing_mode_raw",
                "quantity_mode_raw",
                "runtime_mode",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), total_amount


def _explain_for_target(target_amount: float, period: str, business_file: Path) -> Dict[str, object]:
    resolved_rule = logic.resolve_allocation_rule(rule_template_name="standard", ratios=None)
    all_items = logic.load_config()
    real_data = logic.parse_business_data(
        file_path=str(business_file),
        period=period,
        column_mapping=None,
    )
    actual_qty_map = {name: logic._normalize_qty(q, allow_decimal=False) for name, q in real_data.items()}
    has_report_support = any(("报告" in name and qty > 0) for name, qty in actual_qty_map.items())

    selectable_entries: List[logic._SelectableEntry] = []
    simulated_items = []
    fixed_total = 0.0
    for item in all_items:
        if item.price <= 0:
            continue
        mode = logic._normalize_quantity_mode(item.quantity_mode, item.can_simulate)
        item.quantity_mode = mode
        actual_qty = int(actual_qty_map.get(item.name, 0))
        if mode == "ACTUAL_FULL":
            fixed_total += actual_qty * item.price
        elif mode == "ACTUAL_SELECTABLE":
            selectable_entries.append(logic._SelectableEntry(item=item, actual_qty=actual_qty))
        elif mode == "SIMULATED":
            simulated_items.append(item)

    warnings: List[str] = []
    selectable_amount, feasible = logic._select_actual_quantities(
        entries=selectable_entries,
        target_amount=(target_amount - fixed_total),
        warnings=warnings,
    )
    after_selectable = fixed_total + selectable_amount
    remaining_after_selectable = target_amount - after_selectable
    if remaining_after_selectable < -0.01:
        diff = target_amount - after_selectable
        return {
            "target_amount": round(target_amount, 2),
            "fixed_total": round(fixed_total, 2),
            "selectable_total": round(selectable_amount, 2),
            "simulated_total": 0.0,
            "current_total": round(after_selectable, 2),
            "diff_before_tail": round(diff, 2),
            "tail_threshold": round(float(resolved_rule.get("tail_diff_threshold", 0.0)), 2),
            "exceeds_1_00": "Y" if abs(diff) > 1.0 + 1e-9 else "N",
            "feasible_selectable": "N",
            "sim_item_count": 0,
            "sim_alloc_detail": "",
            "l4_tail_candidates": 0,
            "calc_path": (
                f"fixed({fixed_total:.2f}) + selectable({selectable_amount:.2f}) "
                f"=> over_target({diff:.2f})"
            ),
        }
    max_simulation_ratio = float(resolved_rule.get("max_simulation_ratio", 1.0))
    max_sim_amount = target_amount * max_simulation_ratio
    simulation_pool = simulated_items
    if not has_report_support:
        l3_only = [i for i in simulated_items if i.level == "L3"]
        if l3_only:
            simulation_pool = l3_only

    sim_qty_map, simulated_amount = logic._allocate_simulation(
        remaining_amount=remaining_after_selectable,
        simulated_items=simulation_pool,
        fill_order=resolved_rule.get("fill_order", []),
        max_simulation_amount=max_sim_amount,
    )

    current_total = fixed_total + selectable_amount + simulated_amount
    diff = target_amount - current_total
    effective_tail_threshold = logic._derive_tail_threshold(
        config_threshold=float(resolved_rule.get("tail_diff_threshold", 0.0)),
        selectable_entries=selectable_entries,
        simulated_items=simulation_pool,
    )
    l4_candidates = [i for i in all_items if i.level == "L4" and i.price > 0]

    return {
        "target_amount": round(target_amount, 2),
        "fixed_total": round(fixed_total, 2),
        "selectable_total": round(selectable_amount, 2),
        "simulated_total": round(simulated_amount, 2),
        "current_total": round(current_total, 2),
        "diff_before_tail": round(diff, 2),
        "tail_threshold": round(effective_tail_threshold, 2),
        "exceeds_1_00": "Y" if abs(diff) > 1.0 + 1e-9 else "N",
        "feasible_selectable": "Y" if feasible else "N",
        "sim_item_count": len(simulation_pool),
        "sim_alloc_detail": ";".join(f"{k}:{v}" for k, v in sorted(sim_qty_map.items())),
        "l4_tail_candidates": len(l4_candidates),
        "calc_path": (
            f"fixed({fixed_total:.2f}) + selectable({selectable_amount:.2f}) "
            f"+ simulated({simulated_amount:.2f}) => diff({diff:.2f})"
        ),
    }


def _scan_targets(
    period: str,
    business_file: Path,
    start: int,
    end: int,
    output_csv: Path,
) -> Tuple[int, int]:
    rows: List[Dict[str, object]] = []
    exceed_count = 0
    for target in range(start, end + 1):
        rec = _explain_for_target(float(target), period, business_file)
        rows.append(rec)
        if rec["exceeds_1_00"] == "Y":
            exceed_count += 1

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "target_amount",
                "fixed_total",
                "selectable_total",
                "simulated_total",
                "current_total",
                "diff_before_tail",
                "tail_threshold",
                "exceeds_1_00",
                "feasible_selectable",
                "sim_item_count",
                "sim_alloc_detail",
                "l4_tail_candidates",
                "calc_path",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), exceed_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--business-file",
        default=str(ROOT / "PRD" / "测试业务使用数据.xlsx"),
    )
    parser.add_argument("--period", default="2025-04")
    parser.add_argument("--scan-start", type=int, default=50000)
    parser.add_argument("--scan-end", type=int, default=50030)
    parser.add_argument("--output-dir", default=str(ROOT / "analysis"))
    args = parser.parse_args()

    business_file = Path(args.business_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    line_csv = output_dir / "tail_diff_line_recalc.csv"
    scan_csv = output_dir / "tail_diff_target_scan.csv"
    summary_txt = output_dir / "tail_diff_summary.txt"

    line_rows, line_total = _build_line_recalc(
        business_file=business_file,
        period=args.period,
        output_csv=line_csv,
    )
    scan_rows, exceed_rows = _scan_targets(
        period=args.period,
        business_file=business_file,
        start=args.scan_start,
        end=args.scan_end,
        output_csv=scan_csv,
    )

    summary_lines = [
        f"business_file={business_file}",
        f"period={args.period}",
        f"line_recalc_rows={line_rows}",
        f"line_recalc_total_amount={line_total:.2f}",
        f"target_scan_range={args.scan_start}-{args.scan_end}",
        f"target_scan_rows={scan_rows}",
        f"target_scan_exceeds_1.00={exceed_rows}",
        f"line_csv={line_csv}",
        f"scan_csv={scan_csv}",
    ]
    summary_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
