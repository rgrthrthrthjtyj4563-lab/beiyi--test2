# 对账单智能生成系统 - 项目复盘报告

## 一、项目概述

**项目名称**: 医药合规对账单智能生成引擎  
**核心目标**: 将大额开票金额自动拆解为可审计、可解释的细颗粒度计费清单  
**测试条件**: 输入金额 ¥69,840，使用模板 `@test/业务数据输入模板.xlsx`

---

## 二、核心架构

### 2.1 分层计费模型 (L1-L4)

```
┌─────────────────────────────────────────────────────────────┐
│ L1 系统收费层 (50-60%)                                       │
│ - 医院拜访、商业拜访、API调用等                              │
│ - 单价范围: ¥20-3000                                        │
│ - 计费模式: ACTUAL_FULL / ACTUAL_SELECTABLE                 │
├─────────────────────────────────────────────────────────────┤
│ L2 报告辅助加工 (25-35%)                                     │
│ - 药事报告、竞品分析、市场调研                               │
│ - 单价: ¥3000/人天                                          │
│ - 计费模式: SIMULATED                                       │
├─────────────────────────────────────────────────────────────┤
│ L3 增值服务 (5-15%)                                          │
│ - 大师案例课、专业实务课、知识库                             │
│ - 单价范围: ¥10-500                                         │
│ - 计费模式: SIMULATED                                       │
├─────────────────────────────────────────────────────────────┤
│ L4 其他服务 (0-5%)                                           │
│ - 代理记账、快递服务、资料整理                               │
│ - 单价范围: ¥1-500                                          │
│ - 用途: 尾差调平                                            │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 计费模式详解

| 模式 | 说明 | 适用层级 | 数据要求 |
|------|------|----------|----------|
| **ACTUAL_FULL** | 固定入账，全额计费 | L1 | 需要业务数据 |
| **ACTUAL_SELECTABLE** | 智能择取，可选择部分数量计费 | L1 | 需要业务数据，可设置择取比例范围 |
| **SIMULATED** | 模拟填充，根据剩余金额自动计算数量 | L2/L3/L4 | 无需业务数据 |
| **MANUAL** | 人工录入 | - | 需要人工输入 |

---

## 三、问题根因分析（测试条件：¥69,840）

### 3.1 资金分配流程

```
目标金额: ¥69,840
    ↓
[阶段1] 固定费用 (ACTUAL_FULL)
  结果: ¥0 (无固定费用项)
  剩余: ¥69,840
    ↓
[阶段2] 择取计费 (ACTUAL_SELECTABLE)
  可用项目:
    - 医院拜访: 500次 × ¥30 = ¥15,000 (max)
    - 商业拜访: 50次 × ¥30 = ¥1,500 (max)
    - 医院信息调研管理: 100条 × ¥30 = ¥3,000 (max)
  最大可选: ¥19,500
  结果: ¥19,500
  剩余: ¥50,340
    ↓
[阶段3] 模拟填充 (SIMULATED)
  使用项目:
    - 大师/案例课（A档）: 167节 × ¥300 = ¥50,100
    - 付费课件&精选内容包: 24份 × ¥10 = ¥240
  结果: ¥50,340
    ↓
[阶段4] 尾差调平 (TAIL_BALANCE)
  剩余: ¥0
    ↓
生成金额: ¥69,840 ✅
```

### 3.2 问题诊断

#### ⚠️ 关键发现

1. **业务数据不足**: 模板中的实际业务数据（L1层）只能产生 ¥19,500，仅占目标金额的 27.9%
2. **依赖模拟填充**: 系统必须使用 L3 层的模拟计费项来补足 ¥50,340（72.1%）
3. **分层占比失衡**: 
   - L1: 27.9% (目标 55%) - 偏离 27.1%
   - L2: 0% (目标 30%) - 完全缺失
   - L3: 72.1% (目标 10%) - 超出 62.1%

#### 🔴 潜在风险

如果系统配置不当（如禁用模拟计费项或设置过小的 `max_simulation_ratio`），会出现以下错误：

```python
# 错误场景1: 尾差超过阈值
ValueError: 金额差异 50340.00 超过尾差阈值 10.00，不允许通过 L4 兜底。
# 原因: 剩余金额过大，无法通过 L4 层的小额项目调平

# 错误场景2: 模拟比例限制
# 如果 max_simulation_ratio = 0.5，最大模拟金额 = 69840 × 0.5 = 34920
# 剩余 50340 > 34920，无法完成分配
```

### 3.3 为什么会产生这个问题

1. **数据输入问题**: 模板中的业务数据量太少
   - 医院拜访只有 500 次，如果增加到 1500 次（¥45,000），就能更好地匹配目标金额
   
2. **计费项单价限制**: L1 层单价较低（¥30），需要大量业务数据才能支撑大额对账单
   - 要达到 ¥69,840，仅 L1 层就需要 2328 次拜访

3. **分配策略限制**: 系统设计时要求优先使用实际业务数据，但实际数据不足时只能依赖模拟填充
   - 这导致 L3 层占比异常高

4. **精度匹配问题**: 由于计费项价格是离散的（如 ¥30、¥300、¥10），无法精确匹配任意金额
   - ¥69,840 = 30×500 + 30×50 + 30×100 + 300×167 + 10×24
   - 这是一个"幸运"的组合，某些金额可能无法精确匹配

---

## 四、解决方案

### 4.1 短期解决方案（数据层面）

```python
# 方案1: 增加业务数据量
df = pd.DataFrame({
    '年份': [2026, 2026],
    '月份': [2, 2],
    '服务提供方': ['天津云护', '天津云护'],
    '医院拜访': [1500, 800],  # 增加拜访次数
    '商业拜访': [200, 100],
    # ... 其他字段
})

# 方案2: 调整目标金额到可匹配的范围
# 使用脚本扫描找到可精确匹配的目标金额
```

### 4.2 中期解决方案（配置层面）

```python
# 调整分配规则
{
    "max_simulation_ratio": 1.0,  # 允许100%使用模拟填充
    "tail_diff_threshold": 10000,  # 提高尾差阈值到10000
    "fill_order": ["L2", "L3", "L4"],  # 优先填充L2
    "ratios": {
        "L1": 0.30,  # 降低L1目标占比，接受现实
        "L2": 0.30,
        "L3": 0.35,
        "L4": 0.05
    }
}
```

### 4.3 长期解决方案（架构层面）

1. **增加低单价L4项**: 添加更多小额的L4计费项用于尾差调平
   - 例如：打印快递服务 ¥1/次
   
2. **支持小数数量**: 允许计费数量为浮点数，提高精度
   - 例如：7.8 次拜访 = ¥234
   
3. **动态目标金额**: 系统建议最接近的可匹配金额
   - 输入 ¥69,840 → 建议 ¥69,850（可匹配）

---

## 五、核心代码逻辑

### 5.1 资金分配算法

```python
# backend/logic.py:836-1133

def generate_smart_statement(target_amount, ...):
    # 1. 规范化目标金额（向下取整到10元倍数）
    target = _normalize_target_amount(target_amount)
    
    # 2. 加载业务数据
    quantities = parse_business_data(file_path, period)
    
    # 3. 分类计费项
    fixed_items = []        # ACTUAL_FULL - 固定计费
    selectable_entries = [] # ACTUAL_SELECTABLE - 可选计费
    simulated_items = []    # SIMULATED - 模拟计费
    
    for item in config_items:
        if mode == "ACTUAL_FULL":
            # 直接使用全部实际数量
            fixed_items.append(item)
        elif mode == "ACTUAL_SELECTABLE":
            # 创建择取条目，支持 min/max 比例约束
            entry = _SelectableEntry(item, actual_qty)
            selectable_entries.append(entry)
        elif mode == "SIMULATED":
            # 用于后续模拟填充
            simulated_items.append(item)
    
    # 4. 阶段分配
    fixed_total = sum(i.amount for i in fixed_items)
    remaining = target - fixed_total
    
    # 5. 择取计费（贪心算法）
    selectable_amount, feasible = _select_actual_quantities(
        selectable_entries, remaining, warnings
    )
    
    # 6. 模拟填充
    after_selectable = fixed_total + selectable_amount
    remaining_after_selectable = target - after_selectable
    sim_qty_map, simulated_amount = _allocate_simulation(
        remaining_after_selectable, simulated_items, fill_order, max_sim_amount
    )
    
    # 7. 尾差调平
    current_total = fixed_total + selectable_amount + simulated_amount
    diff = target - current_total
    if abs(diff) > tail_threshold:
        raise ValueError(f"金额差异 {diff} 超过尾差阈值")
    
    # 添加L4尾差调平项
    if abs(diff) > 0.01:
        tail_item = _pick_tail_balance_item(all_items)
        tail_qty = diff / tail_item.price
        statement_items.append(tail_row)
```

### 5.2 择取计费算法

```python
# backend/logic.py:573-609

def _select_actual_quantities(entries, target_amount, warnings):
    """
    从可选条目中选择数量，使计费金额尽可能接近目标金额
    约束条件: min_qty ≤ selected_qty ≤ max_qty
    """
    # 按优先级排序（优先级升序、价格降序、名称升序）
    ranked = sorted(entries, key=lambda e: (
        e.item.pick_priority, 
        -e.item.price, 
        e.item.name
    ))
    
    # 初始化：使用最小数量
    current = sum(e.min_amount for e in entries)
    remaining = target_amount - current
    
    # 贪心填充：每次增加一个步长
    while remaining > 0.01:
        # 找出符合条件的条目（还有剩余容量且能填入剩余金额）
        fit = [
            e for e in ranked
            if e.remaining_capacity >= e.qty_step 
            and (e.item.price * e.qty_step) <= remaining + 1e-9
        ]
        if not fit:
            break
        
        # 选择优先级最高的条目，增加一个步长
        picked = fit[0]
        picked.qty += picked.qty_step
        current += picked.item.price * picked.qty_step
        remaining = target_amount - current
    
    # 如果还有剩余，使用回溯算法微调
    if remaining > 0.01:
        _bounded_backtracking(ranked, remaining)
    
    return current, True
```

---

## 六、关键配置参数

### 6.1 分配规则参数

| 参数 | 默认值 | 说明 | 影响 |
|------|--------|------|------|
| `max_simulation_ratio` | 1.0 | 最大模拟填充比例 | 限制SIMULATED模式的使用比例 |
| `tail_diff_threshold` | 0.0 | 尾差阈值 | 超过此值会报错 |
| `ratio_warning_threshold` | 0.15 | 占比警告阈值 | 分层占比偏离目标时发出警告 |
| `l4_max_ratio` | 0.05 | L4最大占比 | 限制尾差调平的比例 |

### 6.2 计费项参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `quantity_mode` | 数量计算模式 | ACTUAL_FULL / ACTUAL_SELECTABLE / SIMULATED |
| `min_pick_ratio` | 最小择取比例 | 0.2 (至少使用20%的实际数量) |
| `max_pick_ratio` | 最大择取比例 | 0.8 (最多使用80%的实际数量) |
| `pick_priority` | 择取优先级 | 数字越小优先级越高 |

---

## 七、测试验证

### 7.1 回归测试用例

```python
# test_regression.py:41-59

def test_amount_conservation(self):
    """测试金额守恒：生成金额必须等于目标金额"""
    record = main.create_statement(
        target_amount=100000,
        customer="守恒测试客户",
        period="2026-01",
    )
    
    generated = float(record.statement.summary.generated_amount)
    target = float(record.statement.target_amount)
    summed_items = sum(float(x.amount) for x in record.statement.items)
    
    self.assertAlmostEqual(generated, target, places=2)
    self.assertAlmostEqual(summed_items, target, places=2)
```

### 7.2 尾差扫描分析

```bash
# 运行尾差根因分析
python backend/scripts/tail_diff_root_cause_analysis.py \
  --business-file PRD/测试业务使用数据.xlsx \
  --period 2025-04 \
  --scan-start 50000 \
  --scan-end 50030
```

---

## 八、总结与建议

### 8.1 问题本质

用户遇到的 ¥69,840 输入问题，本质是**业务数据与目标金额不匹配**的问题：

1. **数据量不足**: 提供的业务数据只能产生 ¥19,500 的L1层费用
2. **占比失衡**: 72%的金额需要依赖L3层模拟填充，偏离目标占比
3. **精度问题**: 离散的价格体系无法精确匹配任意金额

### 8.2 最佳实践

1. **数据准备**: 提供足够的业务数据，L1层应能覆盖目标金额的 40-60%
2. **目标金额**: 使用系统建议的可匹配金额，或调整金额到最近的匹配值
3. **配置调整**: 根据实际情况调整分层占比目标和尾差阈值
4. **监控预警**: 关注生成后的占比警告，确保符合业务预期

### 8.3 后续优化方向

1. **智能推荐**: 系统根据业务数据自动推荐可匹配的目标金额范围
2. **可视化**: 提供资金分配流程图，直观展示各层占比
3. **数据质量**: 在导入业务数据时进行可行性预检
4. **弹性策略**: 支持更多自定义的分配策略和约束条件

---

## 九、附录

### 9.1 错误代码对照表

| 错误代码 | 说明 | 解决方案 |
|----------|------|----------|
| `FIXED_EXCEEDS_TARGET` | 固定费用超过目标金额 | 减少业务数据或增加目标金额 |
| `SELECTABLE_INFEASIBLE` | 择取约束不可行 | 调整 min/max_pick_ratio |
| `TAIL_DIFF_EXCEEDED` | 尾差超过阈值 | 增加L4项、提高阈值、调整金额 |
| `TAIL_ITEM_MISSING` | 缺少L4尾差承接项 | 启用更多L4计费项 |
| `NO_ENABLED_ITEMS` | 没有启用的计费项 | 检查配置或启用计费项 |

### 9.2 关键文件位置

```
/Users/lee/Documents/beiyi/duizhangdanxitong/
├── backend/
│   ├── logic.py              # 核心算法
│   ├── main.py               # API接口
│   ├── models.py             # 数据模型
│   ├── manager.py            # 对账单管理
│   ├── template_parser.py    # 模板解析
│   └── data/
│       └── config.xlsx       # 计费项配置
├── PRD/
│   ├── V1.0.md               # 需求文档
│   └── 测试业务使用数据.xlsx   # 测试数据
├── test/
│   └── 业务数据输入模板.xlsx   # 输入模板
└── analysis/                 # 分析结果
    ├── tail_diff_summary.txt
    ├── tail_diff_line_recalc.csv
    └── tail_diff_target_scan.csv
```

---

**报告生成时间**: 2026-02-13  
**分析人员**: AI Assistant  
**版本**: v1.0
