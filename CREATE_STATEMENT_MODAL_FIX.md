# CreateStatementModal 修复测试文档

## 修复概要

**问题**: 第103行 `values.statement_date.format('YYYY-MM')` 会导致 `undefined` 错误，因为在第1步时 `values` 只包含当前步骤的表单数据，不包含第0步的 `statement_date`。

**修复**: 使用 `resolvePeriodString(values)` 函数，它会从多个来源获取 `statement_date`：
1. 首先检查传入的 `values` 参数
2. 其次检查 `formData`（第0步保存的数据）
3. 最后使用 `form.getFieldValue('statement_date')`（直接从表单实例获取）

## 代码变更

### 修复前（第103行附近）
```typescript
const checkFeasibility = async (values: any) => {
    const period = values.statement_date?.format('YYYY-MM'); // ❌ 错误：values在第1步不包含statement_date
    // ...
}
```

### 修复后
```typescript
// 第97-103行：新增的resolvePeriodString函数
const resolvePeriodString = (values?: any) => {
    const dateVal = values?.statement_date ?? formData?.statement_date ?? form.getFieldValue('statement_date');
    if (!dateVal || typeof dateVal.format !== 'function') {
      return '';
    }
    return dateVal.format('YYYY-MM');
};

const checkFeasibility = async (values: any) => {
    const period = resolvePeriodString(values); // ✅ 正确：从多个来源获取statement_date
    // ...
}
```

## 测试场景

### 场景1: 标准模板 + 预解析流程

**步骤**:
1. 打开创建对账单模态框
2. 填写基础信息：
   - 客户名称：测试8
   - 账期：2026-02
   - 目标金额：33167
3. 点击"下一步"
4. 选择"标准模板（推荐）"
5. 上传业务明细Excel文件
6. 等待预解析完成
7. 点击"下一步"
8. 查看可行性检查结果

**预期结果**:
- ✅ 不出现 `values.statement_date is undefined` 错误
- ✅ period参数正确传递为 "2026-02"
- ✅ 可行性检查正常执行

### 场景2: 标准模板 + 跳过预解析流程

**步骤**:
1. 打开创建对账单模态框
2. 填写基础信息（同上）
3. 点击"下一步"
4. 选择"标准模板（推荐）"
5. **勾选"跳过预解析，直接下一步"**
6. 上传业务明细Excel文件
7. 点击"下一步"
8. 查看可行性检查结果

**预期结果**:
- ✅ 不出现 `Cannot read property 'format' of undefined` 错误
- ✅ 即使跳过了预解析，也能正确获取账期
- ✅ 可行性检查正常执行

### 场景3: 使用测试数据验证

**测试数据**:
- 客户名称：测试8
- 账期：2026-02
- 目标金额：33167

**验证点**:
1. 在开发者工具Console中不应看到任何 `undefined` 错误
2. 网络请求 `/statements/feasibility` 的FormData中应包含 `period=2026-02`
3. 可行性检查返回结果正常

## 快速验证命令

```bash
# 1. 检查修复后的代码
grep -n "resolvePeriodString" /Users/lee/Documents/beiyi/duizhangdanxitong/frontend/src/components/CreateStatementModal.tsx

# 2. 确保没有危险代码模式（直接使用 values.statement_date.format）
grep -n "values.statement_date.format" /Users/lee/Documents/beiyi/duizhangdanxitong/frontend/src/components/CreateStatementModal.tsx || echo "✅ 已修复"

# 3. 运行测试
cd /Users/lee/Documents/beiyi/duizhangdanxitong/frontend && npm test -- CreateStatementModal.test.tsx
```

## 浏览器端验证

打开浏览器开发者工具，执行以下测试：

```javascript
// 模拟第1步时调用checkFeasibility的场景
// 在Console中输入：

// 测试 resolvePeriodString 是否能正确获取statement_date
const form = document.querySelector('form');
// 验证表单中是否包含账期字段
console.log('账期字段存在:', !!document.querySelector('[name="statement_date"]'));

// 监控API调用
const originalFetch = window.fetch;
window.fetch = function(...args) {
    if (args[0].includes('/feasibility')) {
        console.log('✅ 可行性检查API被调用:', args[0]);
        // 检查FormData
        if (args[1]?.body instanceof FormData) {
            const formData = args[1].body;
            console.log('period参数:', formData.get('period'));
        }
    }
    return originalFetch.apply(this, args);
};
```

## 修复确认清单

- [x] `resolvePeriodString` 函数已添加到第97-103行
- [x] `checkFeasibility` 函数使用 `resolvePeriodString(values)` 代替直接访问 `values.statement_date`
- [x] `handleSubmit` 函数也使用 `resolvePeriodString` 确保一致性
- [x] 代码中没有直接使用 `values.statement_date.format` 的模式
- [x] 测试脚本已创建

## 相关文件

- 修复文件：`/Users/lee/Documents/beiyi/duizhangdanxitong/frontend/src/components/CreateStatementModal.tsx`
- 测试文件：`/Users/lee/Documents/beiyi/duizhangdanxitong/frontend/src/components/CreateStatementModal.test.tsx`

## 回滚方案

如需回滚，只需将第106行：
```typescript
const period = resolvePeriodString(values);
```

改回为：
```typescript
const period = values.statement_date?.format('YYYY-MM');
```

**注意**：回滚会导致bug重新出现，仅用于紧急恢复。
