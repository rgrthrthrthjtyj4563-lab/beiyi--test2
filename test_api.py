#!/usr/bin/env python3
"""
模拟前端调用测试生成API
"""
import sys
sys.path.insert(0, 'backend')

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

print("=== 测试加载计费项 ===")
response = client.get("/settings/billing-items?include_inactive=true")
print(f"Status: {response.status_code}")
if response.status_code == 200:
    items = response.json()
    print(f"成功加载 {len(items)} 个计费项")
else:
    print(f"加载失败: {response.text}")

print("\n=== 测试生成对账单 ===")

# 测试数据
data = {
    'target_amount': 10000.0,
    'customer': '测试客户',
    'period': '2024-01',
    'ratios': '{}',
    'rule_template_name': 'standard',
    'template_name': 'default',
    'mappings_json': '{}',
    'no_data_reason': '测试无业务数据'
}

import io
# 创建一个空的文件对象
empty_file = io.BytesIO(b'')

response = client.post(
    "/statements",
    data=data,
    files={'file': ('test.xlsx', empty_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"生成成功: {response.json()}")
else:
    print(f"生成失败: {response.text}")
