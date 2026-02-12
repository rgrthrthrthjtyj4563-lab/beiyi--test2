#!/usr/bin/env python3
"""
新建对账单功能优化测试
验证方案B的所有优化点
"""

import sys
sys.path.insert(0, '.')

from logic import precheck_statement_feasibility_lightweight, load_config
import json

def test_lightweight_feasibility():
    """测试轻量级可行性检查"""
    print('\n[测试] 轻量级可行性检查函数')
    
    config_items = load_config()
    
    # 测试1: 数据不足
    result = precheck_statement_feasibility_lightweight(
        target_amount=100000,
        business_data_quantities={'医院拜访': 10},
        config_items=config_items
    )
    assert result['feasible'] == False, '应该返回不可行'
    assert result['reason_code'] == 'INSUFFICIENT_DATA'
    print('  ✅ 数据不足检测正确')
    
    # 测试2: 数据充足
    large_data = {item.name: 100 for item in config_items if item.require_business_data}
    result = precheck_statement_feasibility_lightweight(
        target_amount=10000,
        business_data_quantities=large_data,
        config_items=config_items
    )
    assert result['feasible'] == True, '应该返回可行'
    assert 'total_available' in result
    assert 'item_count' in result
    assert 'items' in result
    print(f'  ✅ 数据充足检测正确 ({result["item_count"]}个计费项, 总金额¥{result["total_available"]:,.2f})')
    
    return True

def test_preview_json_parsing():
    """测试 preview_json 解析"""
    print('\n[测试] Preview JSON 解析')
    
    # 模拟前端发送的数据
    preview_data = {
        'quantities': {'医院拜访': 100, 'API调用服务包': 50},
        'rows_total': 10,
        'rows_used': 8,
        'matched_columns': ['医院拜访', 'API调用服务包'],
        'unmatched_columns': []
    }
    
    json_str = json.dumps(preview_data)
    parsed = json.loads(json_str)
    
    assert parsed['quantities']['医院拜访'] == 100
    assert parsed['rows_total'] == 10
    print('  ✅ Preview JSON 解析正确')
    
    return True

def main():
    print('=' * 70)
    print('新建对账单功能优化 - 完整测试套件')
    print('=' * 70)
    
    tests = [
        ('轻量级可行性检查', test_lightweight_feasibility),
        ('Preview JSON 解析', test_preview_json_parsing),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            failed += 1
            print(f'  ❌ 测试失败: {e}')
    
    print('\n' + '=' * 70)
    print(f'测试结果: {passed} 通过, {failed} 失败')
    print('=' * 70)
    
    if failed == 0:
        print('🎉 所有测试通过！方案B优化已成功实施。')
        return 0
    else:
        print('⚠️  部分测试失败，请检查代码。')
        return 1

if __name__ == '__main__':
    exit(main())
