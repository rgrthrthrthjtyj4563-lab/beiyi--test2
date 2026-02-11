import importlib
import json
import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", category=ResourceWarning, message=r"unclosed database.*")


def _clear_backend_modules() -> None:
    for name in ["backend.main", "backend.logic", "backend.manager", "backend.config_store"]:
        if name in sys.modules:
            del sys.modules[name]


def _load_fresh_app(temp_dir: str, legacy_payload: dict | None = None):
    db_path = Path(temp_dir) / "app.db"
    json_path = Path(temp_dir) / "statements_db.json"
    json_path.write_text(json.dumps(legacy_payload or {}, ensure_ascii=False), encoding="utf-8")

    os.environ["SOA_DB_PATH"] = str(db_path)
    os.environ["STATEMENTS_JSON_PATH"] = str(json_path)
    _clear_backend_modules()

    main = importlib.import_module("backend.main")
    logic = importlib.import_module("backend.logic")
    return main, logic


class StatementRegressionTests(unittest.TestCase):
    def test_amount_conservation(self):
        with tempfile.TemporaryDirectory() as td:
            main, _ = _load_fresh_app(td)
            record = main.create_statement(
                target_amount=100000,
                customer="守恒测试客户",
                period="2026-01",
                ratios="{}",
                rule_template_name="standard",
                template_name="default",
                mappings_json="{}",
                no_data_reason="无业务明细",
                file=None,
            )

            generated = float(record.statement.summary.generated_amount)
            target = float(record.statement.target_amount)
            summed_items = sum(float(x.amount) for x in record.statement.items)
            self.assertAlmostEqual(generated, target, places=2)
            self.assertAlmostEqual(summed_items, target, places=2)

    def test_l4_ratio_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            main, _ = _load_fresh_app(td)
            main.put_allocation_rule(
                main.AllocationRuleTemplateUpdate(
                    template_name="standard",
                    strategy_name="equal_split_v1",
                    ratios={"L1": 0.6, "L2": 0.28, "L3": 0.10, "L4": 0.02},
                    l4_max_ratio=0.02,
                    ratio_warning_threshold=0.2,
                    fill_order=["L2", "L3", "L1"],
                )
            )
            record = main.create_statement(
                target_amount=50000,
                customer="边界测试客户",
                period="2026-02",
                ratios="{}",
                rule_template_name="standard",
                template_name="default",
                mappings_json="{}",
                no_data_reason="无业务明细",
                file=None,
            )
            l4_ratio = float(record.statement.summary.layers["L4"]["ratio"])
            self.assertLessEqual(l4_ratio, 0.021)

    def test_parse_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            _, logic = _load_fresh_app(td)
            config_items = logic.load_config()
            self.assertGreater(len(config_items), 0)
            target_item_name = config_items[0].name

            df = pd.DataFrame(
                {
                    "年份": [2026, 2026, 2026],
                    "月份": [1, 1, 2],
                    "服务提供方": ["A", "B", "C"],
                    "外部字段": [10, 20, 30],
                }
            )
            excel_path = Path(td) / "biz.xlsx"
            df.to_excel(excel_path, index=False)

            parsed = logic.parse_business_data_preview(
                file_path=str(excel_path),
                period="2026-01",
                config_items=config_items,
                column_mapping={"外部字段": target_item_name},
            )

            self.assertEqual(parsed["rows_total"], 3)
            self.assertEqual(parsed["rows_used"], 2)
            self.assertIn(f"外部字段->{target_item_name}", parsed["matched_columns"])
            self.assertAlmostEqual(float(parsed["quantities"][target_item_name]), 30.0, places=6)

    def test_create_and_export_api_flow(self):
        with tempfile.TemporaryDirectory() as td:
            main, _ = _load_fresh_app(td)
            record = main.create_statement(
                target_amount=32100,
                customer="集成测试客户",
                period="2026-03",
                ratios="{}",
                rule_template_name="standard",
                template_name="default",
                mappings_json="{}",
                no_data_reason="无业务明细",
                file=None,
            )

            self.assertEqual(record.status, "DRAFT")
            export_resp = main.export_statement_file(record.id)
            self.assertEqual(export_resp.status_code, 200)
            self.assertTrue(Path(export_resp.path).exists())

            updated = main.get_statement(record.id)
            self.assertEqual(updated.status, "EXPORTED")
            self.assertTrue(any(h.get("action") == "EXPORT" for h in updated.history))

            try:
                Path(export_resp.path).unlink(missing_ok=True)
            except Exception:
                pass

    def test_json_migration_once(self):
        with tempfile.TemporaryDirectory() as td:
            legacy_id = "legacy-001"
            legacy_payload = {
                legacy_id: {
                    "id": legacy_id,
                    "status": "DRAFT",
                    "created_at": "2026-02-11T00:00:00",
                    "updated_at": "2026-02-11T00:00:00",
                    "statement": {
                        "customer": "历史客户",
                        "period": "2026-01",
                        "target_amount": 100.0,
                        "summary": {
                            "target_amount": 100.0,
                            "generated_amount": 100.0,
                            "diff": 0.0,
                            "layers": {
                                "L1": {"amount": 100.0, "ratio": 1.0},
                                "L2": {"amount": 0.0, "ratio": 0.0},
                                "L3": {"amount": 0.0, "ratio": 0.0},
                                "L4": {"amount": 0.0, "ratio": 0.0},
                            },
                            "warnings": [],
                        },
                        "items": [
                            {
                                "level": "L1",
                                "name": "历史项",
                                "unit": "次",
                                "price": 100.0,
                                "quantity": 1.0,
                                "amount": 100.0,
                                "source": "系统固定",
                            }
                        ],
                    },
                    "history": [
                        {
                            "timestamp": "2026-02-11T00:00:00",
                            "action": "CREATED",
                            "note": "Initial generation",
                        }
                    ],
                }
            }

            main, _ = _load_fresh_app(td, legacy_payload=legacy_payload)
            migrated = main.get_statement(legacy_id)
            self.assertIsNotNone(migrated)
            self.assertEqual(migrated.statement.customer, "历史客户")

            with main.manager._connect() as conn:
                migration_rows = conn.execute(
                    "SELECT COUNT(1) AS c FROM statement_migrations WHERE migration_key = ?",
                    ("statements_json_to_sqlite_v1",),
                ).fetchone()
            self.assertEqual(int(migration_rows["c"]), 1)


if __name__ == "__main__":
    unittest.main()
