#!/usr/bin/env python3
"""测试脚本来重现生成失败错误"""

import sys
sys.path.insert(0, 'backend')

from logic import generate_smart_statement, load_config

# 打印当前计费项
print("=== 当前计费项 ===")
items = load_config()
for item in items:
    print(f"  {item.name}: level={item.level}, price={item.price}, can_simulate={item.can_simulate}")

print(f"\n总计费项数量: {len(items)}")

# 尝试生成对账单
print("\n=== 尝试生成对账单 ===")
try:
    stmt = generate_smart_statement(
        target_amount=10000.0,
        customer="测试客户",
        period="2024-01",
        ratios=None,
        business_data_file=None,
        column_mapping=None,
        rule_template_name="standard"
    )
    print(f"生成成功！")
    print(f"  客户: {stmt.customer}")
    print(f"  金额: {stmt.target_amount}")
    print(f"  项目数: {len(stmt.items)}")
except Exception as e:
    print(f"生成失败: {e}")
    import traceback
    traceback.print_exc()
