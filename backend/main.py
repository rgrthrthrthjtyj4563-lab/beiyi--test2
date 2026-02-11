from fastapi import FastAPI, HTTPException, Body, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from backend.logic import (
    load_config,
    generate_smart_statement,
    load_config_seed_payload,
    parse_business_data_preview,
    get_allocation_strategies,
    resolve_allocation_rule,
)
from backend.models import (
    Statement,
    BillingItem,
    BillingItemConfig,
    BillingItemConfigCreate,
    BillingItemConfigUpdate,
    BusinessDataPreview,
    DataSourceRecord,
    FieldMappingTemplate,
    FieldMappingTemplateUpdate,
    AllocationRuleTemplate,
    AllocationRuleTemplateUpdate,
    AllocationRuleVersion,
    AllocationStrategyOption,
)
from backend.manager import StatementManager, StatementRecord
from backend.config_store import config_store
from openpyxl import load_workbook
import tempfile
import os
import shutil
import json
from pathlib import Path
from datetime import datetime
from copy import copy

app = FastAPI(title="Smart Statement Generator")
manager = StatementManager()

# Seed dynamic config table from existing excel config on first run.
config_store.seed_billing_items(load_config_seed_payload())
config_store.backfill_item_meta(load_config_seed_payload())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "PRD" / "Statement of Account.xlsx"


def _format_period_label(period: str) -> str:
    p = (period or "").strip().upper()
    if "-Q" in p:
        try:
            y, q = p.split("-Q")
            return f"{int(y)}年Q{int(q)}"
        except Exception:
            return period
    if "-" in p:
        try:
            y, m = p.split("-")
            return f"{int(y)}年{int(m)}月"
        except Exception:
            return period
    return period


def _level_label(level: str) -> str:
    mapping = {
        "L1": "L1系统收费层",
        "L2": "L2报告辅助加工",
        "L3": "L3增值服务",
        "L4": "L4其他服务",
    }
    return mapping.get(level, level)


def _unit_label(unit: str) -> str:
    if "/" in (unit or ""):
        return unit.split("/")[-1]
    return unit or ""


def _load_item_meta() -> dict:
    meta = {}
    db_items = config_store.list_billing_items(include_inactive=True)
    for item in db_items:
        name = str(item.get("name", "")).strip()
        if not name or name in meta:
            continue
        meta[name] = {
            "category": str(item.get("category", "") or ""),
            "reason": str(item.get("billing_note", "") or ""),
        }
    return meta


def _payload_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _fill_statement_template(statement: Statement) -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    wb = load_workbook(TEMPLATE_PATH)
    ws = wb[wb.sheetnames[0]]

    ws["A2"] = statement.customer
    ws["B2"] = _format_period_label(statement.period)
    ws["C2"] = f"{statement.target_amount:,.2f}元"
    ws["D2"] = datetime.now().strftime("%Y-%m-%d")

    item_meta = _load_item_meta()
    items = statement.items

    start_row = 5
    base_detail_rows = 14
    if len(items) > base_detail_rows:
        extra_rows = len(items) - base_detail_rows
        ws.insert_rows(19, amount=extra_rows)
        # Keep inserted detail rows visually consistent with template.
        for offset in range(extra_rows):
            dst = 19 + offset
            src = 18
            for col in range(1, 10):
                ws.cell(dst, col)._style = copy(ws.cell(src, col)._style)

    detail_end_row = start_row + max(base_detail_rows, len(items)) - 1
    for row in range(start_row, detail_end_row + 1):
        for col in range(1, 10):
            ws.cell(row, col, None)

    for idx, item in enumerate(items, start=start_row):
        meta = item_meta.get(item.name, {})
        ws.cell(idx, 1, _level_label(item.level))
        ws.cell(idx, 2, meta.get("category", ""))
        ws.cell(idx, 3, item.name)
        ws.cell(idx, 4, _unit_label(item.unit))
        ws.cell(idx, 5, item.quantity)
        ws.cell(idx, 6, item.price)
        ws.cell(idx, 7, item.amount)
        ws.cell(idx, 8, item.source)
        ws.cell(idx, 9, meta.get("reason", ""))

    total_row = start_row + len(items)
    clear_to = max(total_row + 4, 23)
    for row in range(total_row, clear_to + 1):
        for col in range(1, 10):
            ws.cell(row, col, None)

    ws.cell(total_row, 1, "合计")
    if items:
        ws.cell(total_row, 7, f"=SUM(G{start_row}:G{total_row - 1})")
    else:
        ws.cell(total_row, 7, 0)

    layer_labels = {
        "L1": "L1系统收费层 小计",
        "L2": "L2报告辅助加工 小计",
        "L3": "L3增值服务 小计",
        "L4": "L4其他服务 小计",
    }
    for i, level in enumerate(["L1", "L2", "L3", "L4"], start=1):
        row = total_row + i
        layer = statement.summary.layers.get(level, {"amount": 0, "ratio": 0})
        ws.cell(row, 1, layer_labels[level])
        ws.cell(row, 7, layer.get("amount", 0))
        ws.cell(row, 9, f"占比 {float(layer.get('ratio', 0)) * 100:.2f}%")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        wb.save(tmp.name)
        return tmp.name

@app.get("/config", response_model=list[BillingItem])
def get_config():
    return load_config()


@app.get("/settings/billing-items", response_model=list[BillingItemConfig])
def list_billing_items(include_inactive: bool = False):
    items = config_store.list_billing_items(include_inactive=include_inactive)
    return [BillingItemConfig(**i) for i in items]


@app.post("/settings/billing-items", response_model=BillingItemConfig)
def create_billing_item(payload: BillingItemConfigCreate):
    try:
        item = config_store.create_billing_item(_payload_dict(payload))
        return BillingItemConfig(**item)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/settings/billing-items/{item_id}", response_model=BillingItemConfig)
def update_billing_item(item_id: int, payload: BillingItemConfigUpdate):
    data = {k: v for k, v in _payload_dict(payload).items() if v is not None}
    item = config_store.update_billing_item(item_id, data)
    if not item:
        raise HTTPException(status_code=404, detail="Billing item not found")
    return BillingItemConfig(**item)


@app.post("/settings/billing-items/{item_id}/deactivate", response_model=BillingItemConfig)
def deactivate_billing_item(item_id: int):
    item = config_store.deactivate_billing_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Billing item not found")
    return BillingItemConfig(**item)

# Legacy endpoint - keeping it for compatibility or quick test
@app.post("/generate", response_model=Statement)
def generate_statement_legacy(
    target_amount: float = Body(..., embed=True),
    customer: str = Body(..., embed=True),
    period: str = Body(..., embed=True),
    ratios: dict = Body({'L1': 0.55, 'L2': 0.30, 'L3': 0.10, 'L4': 0.05}, embed=True)
):
    try:
        return generate_smart_statement(
            target_amount=target_amount,
            customer=customer,
            period=period,
            ratios=ratios,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/business-data/preview", response_model=BusinessDataPreview)
def preview_business_data(
    period: str = Form(default=""),
    template_name: str = Form(default="default"),
    mappings_json: str = Form(default="{}"),
    file: UploadFile = File(...),
):
    temp_file_path = None
    try:
        try:
            request_mapping = json.loads(mappings_json or "{}")
        except Exception:
            request_mapping = {}

        template_mapping = config_store.list_field_mappings(template_name=template_name)
        merged_mapping = {**template_mapping, **(request_mapping or {})}

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_file_path = tmp.name

        parsed = parse_business_data_preview(
            file_path=temp_file_path,
            period=period,
            config_items=load_config(),
            column_mapping=merged_mapping,
        )
        return BusinessDataPreview(**parsed)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


# New Lifecycle Endpoints
@app.get("/statements", response_model=list[StatementRecord])
def list_statements():
    return manager.list()

@app.post("/statements", response_model=StatementRecord)
def create_statement(
    target_amount: float = Form(...),
    customer: str = Form(...),
    period: str = Form(...),
    ratios: str = Form(default="{}"),
    rule_template_name: str = Form(default="standard"),
    template_name: str = Form(default="default"),
    mappings_json: str = Form(default="{}"),
    no_data_reason: str = Form(default=""),
    file: UploadFile = File(default=None),
):
    try:
        if not file and not no_data_reason.strip():
            raise HTTPException(status_code=400, detail="请上传业务明细，或填写无明细原因")

        # Parse ratios
        try:
            parsed_ratios = json.loads(ratios or "{}")
            ratios_dict = parsed_ratios if isinstance(parsed_ratios, dict) and parsed_ratios else None
        except:
            ratios_dict = None

        try:
            request_mapping = json.loads(mappings_json or "{}")
        except Exception:
            request_mapping = {}
        template_mapping = config_store.list_field_mappings(template_name=template_name)
        merged_mapping = {**template_mapping, **(request_mapping or {})}
            
        # Handle file upload
        temp_file_path = None
        file_name = None
        preview_result = None
        if file:
            file_name = file.filename
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_file_path = tmp.name
            preview_result = parse_business_data_preview(
                file_path=temp_file_path,
                period=period,
                config_items=load_config(),
                column_mapping=merged_mapping,
            )
        
        try:
            resolved_rule = resolve_allocation_rule(
                rule_template_name=rule_template_name,
                ratios=ratios_dict,
            )
            stmt = generate_smart_statement(
                target_amount, 
                customer, 
                period, 
                ratios_dict,
                business_data_file=temp_file_path,
                column_mapping=merged_mapping,
                rule_template_name=rule_template_name,
            )
            record = manager.create(
                stmt,
                rule_template_name=str(resolved_rule.get("template_name", rule_template_name)),
                rule_template_version=int(resolved_rule.get("version", 1)),
                rule_strategy_name=str(resolved_rule.get("strategy_name", "")),
                rule_snapshot=resolved_rule,
            )
            source_payload = {
                "statement_id": record.id,
                "source_type": "BUSINESS_FILE" if file else "MANUAL_REASON",
                "source_name": file_name,
                "period": period,
                "no_data_reason": no_data_reason.strip() or None,
                "rows_total": (preview_result or {}).get("rows_total", 0),
                "rows_used": (preview_result or {}).get("rows_used", 0),
                "matched_columns": len((preview_result or {}).get("matched_columns", [])),
                "unmatched_columns": len((preview_result or {}).get("unmatched_columns", [])),
            }
            config_store.create_data_source(source_payload)
            return record
        finally:
            # Clean up temp file
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/statements/{id}", response_model=StatementRecord)
def get_statement(id: str):
    record = manager.get(id)
    if not record:
        raise HTTPException(status_code=404, detail="Statement not found")
    return record


@app.get("/statements/{id}/sources", response_model=list[DataSourceRecord])
def get_statement_sources(id: str):
    record = manager.get(id)
    if not record:
        raise HTTPException(status_code=404, detail="Statement not found")
    rows = config_store.list_statement_sources(id)
    return [DataSourceRecord(**r) for r in rows]


@app.get("/settings/field-mappings", response_model=FieldMappingTemplate)
def get_field_mappings(template_name: str = "default"):
    mappings = config_store.list_field_mappings(template_name=template_name)
    return FieldMappingTemplate(template_name=template_name, mappings=mappings)


@app.put("/settings/field-mappings", response_model=FieldMappingTemplate)
def put_field_mappings(payload: FieldMappingTemplateUpdate):
    saved = config_store.replace_field_mappings(
        template_name=payload.template_name,
        mappings=payload.mappings,
    )
    return FieldMappingTemplate(template_name=payload.template_name, mappings=saved)


@app.get("/settings/allocation-rules", response_model=AllocationRuleTemplate)
def get_allocation_rule(template_name: str = "standard"):
    rule = config_store.get_allocation_rule(template_name=template_name)
    return AllocationRuleTemplate(**rule)


@app.put("/settings/allocation-rules", response_model=AllocationRuleTemplate)
def put_allocation_rule(payload: AllocationRuleTemplateUpdate):
    saved = config_store.upsert_allocation_rule(_payload_dict(payload))
    return AllocationRuleTemplate(**saved)


@app.get("/settings/allocation-rules/versions", response_model=list[AllocationRuleVersion])
def list_allocation_rule_versions(template_name: str = "standard", limit: int = 20):
    rows = config_store.list_allocation_rule_versions(template_name=template_name, limit=limit)
    return [AllocationRuleVersion(**r) for r in rows]


@app.get("/settings/allocation-strategies", response_model=list[AllocationStrategyOption])
def list_allocation_strategies():
    return [AllocationStrategyOption(**x) for x in get_allocation_strategies()]

@app.post("/statements/{id}/export")
def export_statement_file(id: str):
    record = manager.get(id)
    if not record:
        raise HTTPException(status_code=404, detail="Statement not found")
    
    statement = record.statement
    try:
        output_path = _fill_statement_template(statement)
        manager.update_status(id, "export", "Exported template attachment")
        return FileResponse(
            output_path,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=f"Statement of Account_{statement.customer}_{statement.period}.xlsx"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
