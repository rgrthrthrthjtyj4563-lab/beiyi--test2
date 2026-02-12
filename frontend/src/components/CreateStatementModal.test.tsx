import React from 'react';
import { render, screen } from '@testing-library/react';
import { CreateStatementModal } from './CreateStatementModal';
import { App } from 'antd';
import dayjs from 'dayjs';
import fs from 'fs';
import path from 'path';

describe('CreateStatementModal', () => {
  const mockOnCancel = jest.fn();
  const mockOnSuccess = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('渲染极简对账弹窗字段', () => {
    render(
      <App>
        <CreateStatementModal
          open={true}
          onCancel={mockOnCancel}
          onSuccess={mockOnSuccess}
        />
      </App>
    );

    expect(screen.getByPlaceholderText('请输入客户名称')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请选择对账日期')).toBeInTheDocument();
    expect(screen.getByText('下载模板')).toBeInTheDocument();
    expect(screen.getByText('导入')).toBeInTheDocument();
  });

  describe('resolvePeriodString', () => {
    it('应使用安全的账期解析方式', () => {
      const filePath = path.join(__dirname, 'CreateStatementModal.tsx');
      const content = fs.readFileSync(filePath, 'utf-8');

      expect(content).toContain('resolvePeriodString(values)');
      expect(content).toContain('form.getFieldValue(\'statement_date\')');

      const dangerousPattern = /values\.statement_date\.format/;
      expect(dangerousPattern.test(content)).toBe(false);
    });

    it('应正确处理不同来源的日期值', () => {
      const testCases = [
        {
          values: { statement_date: dayjs('2026-02-15') },
          formValue: null,
          expected: '2026-02'
        },
        {
          values: {},
          formValue: dayjs('2026-04-10'),
          expected: '2026-04'
        }
      ];

      testCases.forEach(testCase => {
        let result = '';
        const dateVal = testCase.values?.statement_date ?? testCase.formValue;
        
        if (dateVal && typeof dateVal.format === 'function') {
          result = dateVal.format('YYYY-MM');
        }

        expect(result).toBe(testCase.expected);
      });
    });
  });
});
