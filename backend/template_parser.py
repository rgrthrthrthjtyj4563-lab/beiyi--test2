import pandas as pd
from typing import Dict, List, Optional
from pathlib import Path

try:
    from .logic import load_config, _safe_float
    from .models import BillingItem
except ImportError:
    from logic import load_config, _safe_float
    from models import BillingItem


def _template_items(config_items: List[BillingItem]) -> List[BillingItem]:
    return [item for item in config_items if item.require_business_data]


def _l1_template_items(config_items: List[BillingItem]) -> List[BillingItem]:
    return [item for item in config_items if item.require_business_data and item.level == "L1"]


def generate_standard_input_template(output_path: str) -> str:
    """生成标准化的业务数据输入模板
    
    模板特点：
    1. 列名直接使用计费项名称，无需模糊匹配
    2. 只需填写数量，无需其他字段
    3. 支持多账期数据（可选）
    """
    config_items = load_config()
    template_items = _template_items(config_items)
    
    # 基础列（必需）
    columns = ['年份', '月份', '服务提供方']  # 用于账期筛选与审计归档
    
    level_order = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}
    template_items = sorted(
        template_items,
        key=lambda item: (level_order.get(item.level, 9), item.pick_priority or 999, item.name),
    )

    for item in template_items:
        columns.append(item.name)
    
    # 创建示例数据
    example_data = {
        '年份': [2024, 2024],
        '月份': [1, 2],
        '服务提供方': ['示例服务商A', '示例服务商B'],
    }
    
    for item in template_items:
        example_data[item.name] = [0, 0]
    
    df = pd.DataFrame(example_data)
    
    # 添加说明sheet
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # 数据sheet
        df.to_excel(writer, sheet_name='业务数据', index=False)
        
        # 说明sheet
        readme_data = {
            '字段': ['年份', '月份', '服务提供方'] + [item.name for item in template_items],
            '说明': [
                '数据所属年份（必填，用于筛选）',
                '数据所属月份（必填，用于筛选）',
                '服务商/供应方名称（必填）',
            ] + [
                f'{item.level}层 - {item.unit} - 单价¥{item.price}'
                for item in template_items
            ],
            '层级': ['', '', ''] + [item.level for item in template_items],
            '计量单位': ['', '', ''] + [item.unit for item in template_items],
            '单价(元)': ['', '', ''] + [item.price for item in template_items],
            '计费模式': ['', '', ''] + [item.billing_mode for item in template_items],
            '需业务数据': ['', '', ''] + [('是' if item.require_business_data else '否') for item in template_items],
            '择取比例最小': ['', '', ''] + [item.min_pick_ratio for item in template_items],
            '择取比例最大': ['', '', ''] + [item.max_pick_ratio for item in template_items],
            '择取优先级': ['', '', ''] + [item.pick_priority for item in template_items],
            '备注/口径': ['', '', ''] + [item.billing_note for item in template_items],
            '示例': ['2024', '1', '示例服务商A'] + ['10'] * len(template_items),
        }
        readme_df = pd.DataFrame(readme_data)
        readme_df.to_excel(writer, sheet_name='填写说明', index=False)
    
    return output_path


def parse_standard_template(
    file_path: str,
    period: Optional[str] = None,
    config_items: Optional[List[BillingItem]] = None,
) -> Dict:
    """解析标准模板（简化版解析，无需模糊匹配）
    
    优点：
    1. 列名直接匹配，速度快
    2. 无需字段映射配置
    3. 解析逻辑简单，不易出错
    """
    if config_items is None:
        config_items = load_config()
    template_items = _template_items(config_items)
    valid_names = {item.name for item in template_items}
    
    try:
        # 只读取必要的列（年份、月份和所有计费项）
        usecols = ['年份', '月份', '服务提供方'] + list(valid_names)
        try:
            df = pd.read_excel(file_path, engine="calamine", usecols=lambda x: x in usecols)
        except Exception:
            df = pd.read_excel(file_path, usecols=lambda x: x in usecols)
    except Exception as e:
        return {
            "success": False,
            "error": f"读取文件失败: {str(e)}",
            "quantities": {},
        }
    
    rows_total = len(df)
    
    # 账期筛选
    if period and '年份' in df.columns:
        try:
            year, month = period.split('-')
            year = int(year)
            month = int(month)
            
            df = df[df['年份'] == year]
            if '月份' in df.columns:
                df = df[df['月份'] == month]
        except:
            pass
    
    rows_used = len(df)
    
    # 直接读取计费项数量（无需匹配）
    quantities = {}
    matched_columns = []
    unmatched_columns = []
    
    for col in df.columns:
        if col in ['年份', '月份', '服务提供方']:
            continue
        
        if col in valid_names:
            total = _safe_float(df[col].sum(), 0.0)
            if total > 0:
                quantities[col] = total
            matched_columns.append(col)
        else:
            unmatched_columns.append(col)
    
    return {
        "success": True,
        "period": period or "",
        "rows_total": rows_total,
        "rows_used": rows_used,
        "matched_columns": matched_columns,
        "unmatched_columns": unmatched_columns,
        "quantities": quantities,
        "is_standard_template": True,
    }


def parse_standard_template_l1(
    file_path: str,
    period: Optional[str] = None,
    config_items: Optional[List[BillingItem]] = None,
) -> Dict:
    if config_items is None:
        config_items = load_config()
    template_items = _l1_template_items(config_items)
    valid_names = [item.name for item in template_items]

    try:
        usecols = ['年份', '月份', '服务提供方'] + valid_names
        try:
            df = pd.read_excel(file_path, engine="calamine", usecols=lambda x: x in usecols)
        except Exception:
            df = pd.read_excel(file_path, usecols=lambda x: x in usecols)
    except Exception as e:
        return {
            "success": False,
            "error": f"读取文件失败: {str(e)}",
            "rows": [],
        }

    rows_total = len(df)

    if period and '年份' in df.columns:
        try:
            year, month = period.split('-')
            year = int(year)
            month = int(month)

            df = df[df['年份'] == year]
            if '月份' in df.columns:
                df = df[df['月份'] == month]
        except:
            pass

    rows_used = len(df)

    rows = []
    for name in valid_names:
        if name in df.columns:
            total = _safe_float(df[name].sum(), 0.0)
        else:
            total = 0.0
        rows.append({"name": name, "quantity": total})

    return {
        "success": True,
        "period": period or "",
        "rows_total": rows_total,
        "rows_used": rows_used,
        "columns": ["名称", "数量"],
        "rows": rows,
        "is_standard_template": True,
        "level": "L1",
    }


def validate_standard_template(file_path: str) -> Dict:
    """验证文件是否符合标准模板格式"""
    try:
        try:
            df = pd.read_excel(file_path, engine="calamine", nrows=0)
        except Exception:
            df = pd.read_excel(file_path, nrows=0)  # 只读取表头
        columns = set(df.columns)
        
        config_items = load_config()
        required_columns = {'年份', '月份', '服务提供方'}
        expected_item_columns = {item.name for item in config_items if item.require_business_data}
        expected_columns = required_columns | expected_item_columns
        
        # 检查是否包含计费项列
        billing_columns = columns & expected_item_columns
        missing_required = list(required_columns - columns)
        
        return {
            "is_valid": (len(missing_required) == 0)
            and (len(expected_item_columns) == 0 or len(billing_columns) > 0),
            "match_ratio": (len(billing_columns) / len(expected_item_columns)) if expected_item_columns else 1.0,
            "matched_columns": list(billing_columns),
            "missing_columns": list(expected_columns - columns),
            "missing_required_columns": missing_required,
            "missing_item_columns": list(expected_item_columns - columns),
            "extra_columns": list(columns - expected_columns),
        }
    except Exception as e:
        return {
            "is_valid": False,
            "error": str(e),
        }
