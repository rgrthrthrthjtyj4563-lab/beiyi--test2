import React, { useState, useEffect, useCallback } from 'react';
import { Table, Button, Tag, Space, Tooltip, Input, Card, App, Progress } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined, ExportOutlined, PlusOutlined } from '@ant-design/icons';
import axios from 'axios';
import styled from 'styled-components';
import { apiUrl } from '../lib/api';
import dayjs from 'dayjs';
import JSZip from 'jszip';
import { saveAs } from 'file-saver';

const Container = styled.div`
  padding: 24px;
`;

const Toolbar = styled.div`
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 16px;
  flex-wrap: wrap;
`;

const FilterGroup = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
`;

interface Statement {
  id: string;
  customer_name: string;
  statement_date: string; // YYYY-MM
  target_amount: number;
  actual_amount: number;
  is_match: boolean;
  export_status: 'pending' | 'exported' | 'failed';
  updated_at: string;
}

interface StatementRecordsProps {
  onNavigate: (id: string) => void;
  onCreate: () => void;
  refreshKey?: number;
}

export const StatementRecords: React.FC<StatementRecordsProps> = ({ onNavigate, onCreate, refreshKey }) => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Statement[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchExporting, setBatchExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const { message } = App.useApp();
  
  // Filters
  const [searchText, setSearchText] = useState('');
  
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // In a real app, we would pass filter params here
      const res = await axios.get(apiUrl('/statements'));
      setData(res.data.map((item: any) => {
        const statement = item.statement || {};
        const targetAmount = Number(statement.target_amount ?? item.target_amount ?? 0);
        const actualAmount = Number(statement.summary?.generated_amount ?? item.actual_amount ?? 0);
        const status = String(item.status || '').toUpperCase();
        const exportStatus = status === 'EXPORTED' ? 'exported' : 'pending';
        const updatedAt = item.updated_at || item.created_at || new Date().toISOString();
        return {
          id: item.id,
          customer_name: statement.customer || item.customer_name || 'Unknown Customer',
          statement_date: statement.period || item.statement_date || '2023-01',
          target_amount: targetAmount,
          actual_amount: actualAmount,
          is_match: Math.abs(targetAmount - actualAmount) < 0.01,
          export_status: exportStatus,
          updated_at: updatedAt,
        };
      }));
    } catch (e) {
      console.error(e);
      message.error('Failed to load statements');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    loadData();
  }, [loadData, refreshKey]);

  const filteredData = searchText
    ? data.filter((item) => item.customer_name.toLowerCase().includes(searchText.toLowerCase()))
    : data;

  const columns: ColumnsType<Statement> = [
    {
      title: '客户名称',
      dataIndex: 'customer_name',
      key: 'customer_name',
      fixed: 'left',
      width: 150,
      sorter: (a, b) => a.customer_name.localeCompare(b.customer_name),
    },
    {
      title: '账期',
      dataIndex: 'statement_date',
      key: 'statement_date',
      fixed: 'left',
      width: 120,
      sorter: (a, b) => a.statement_date.localeCompare(b.statement_date),
    },
    {
      title: '目标金额',
      dataIndex: 'target_amount',
      key: 'target_amount',
      align: 'right',
      width: 150,
      render: (val) => `¥${val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
      sorter: (a, b) => a.target_amount - b.target_amount,
    },
    {
      title: '实际生成后金额',
      dataIndex: 'actual_amount',
      key: 'actual_amount',
      align: 'right',
      width: 150,
      render: (val, record) => {
        const diff = Math.abs(val - record.target_amount);
        const color = diff > 0.01 ? 'red' : 'inherit';
        return <span style={{ color, fontWeight: diff > 0.01 ? 'bold' : 'normal' }}>
          ¥{val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
        </span>;
      },
    },
    {
      title: '金额一致',
      dataIndex: 'is_match',
      key: 'is_match',
      align: 'center',
      width: 100,
      render: (match) => (
        <Tag color={match ? 'green' : 'red'}>
          {match ? '一致' : '不一致'}
        </Tag>
      ),
      filters: [
        { text: '一致', value: true },
        { text: '不一致', value: false },
      ],
      onFilter: (value, record) => record.is_match === value,
    },
    {
      title: '导出状态',
      dataIndex: 'export_status',
      key: 'export_status',
      width: 120,
      render: (status) => {
        const colors = { pending: 'default', exported: 'blue', failed: 'error' };
        const labels = { pending: '未导出', exported: '已导出', failed: '失败' };
        return <Tag color={colors[status as keyof typeof colors]}>{labels[status as keyof typeof labels]}</Tag>;
      },
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      align: 'right',
      width: 180,
      render: (val) => (
        <Tooltip title={dayjs(val).format('YYYY-MM-DD HH:mm:ss')}>
          {dayjs(val).format('YYYY-MM-DD HH:mm')}
        </Tooltip>
      ),
      sorter: (a, b) => new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime(),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 100,
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => onNavigate(record.id)}>
          查看
        </Button>
      ),
    },
  ];

  const handleBatchExport = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请选择要导出的记录');
      return;
    }

    setBatchExporting(true);
    setExportProgress(0);
    const zip = new JSZip();
    const total = selectedRowKeys.length;
    let successCount = 0;
    let failCount = 0;

    try {
      for (let i = 0; i < selectedRowKeys.length; i++) {
        const id = selectedRowKeys[i] as string;
        const record = data.find((item) => item.id === id);

        try {
          const res = await axios.post(
            apiUrl(`/statements/${id}/export`),
            {},
            { responseType: 'blob' }
          );

          const blob = new Blob([res.data], {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          });

          const fileName = record
            ? `Statement of Account_${record.customer_name}_${record.statement_date}.xlsx`
            : `Statement_${id}.xlsx`;

          zip.file(fileName, blob);
          successCount++;
        } catch (error) {
          console.error(`Failed to export statement ${id}:`, error);
          failCount++;
        }

        setExportProgress(Math.round(((i + 1) / total) * 100));
      }

      if (successCount === 0) {
        message.error('所有导出请求均失败，请检查网络或服务器状态');
        return;
      }

      const zipBlob = await zip.generateAsync({
        type: 'blob',
        compression: 'DEFLATE',
        compressionOptions: { level: 6 },
      });

      const timestamp = dayjs().format('YYYYMMDD_HHmmss');
      saveAs(zipBlob, `Statements_Batch_Export_${timestamp}.zip`);

      if (failCount > 0) {
        message.warning(`导出完成: ${successCount} 成功, ${failCount} 失败`);
      } else {
        message.success(`成功导出 ${successCount} 条对账单`);
      }

      setSelectedRowKeys([]);
    } catch (error) {
      console.error('Batch export failed:', error);
      message.error('批量导出失败');
    } finally {
      setBatchExporting(false);
      setExportProgress(0);
    }
  };

  return (
    <Container>
      <Toolbar>
        <FilterGroup>
          <Input.Search 
            placeholder="搜索客户名称" 
            onSearch={val => setSearchText(val)} 
            style={{ width: 200 }} 
            allowClear
            onChange={e => { if(!e.target.value) setSearchText('') }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadData} disabled={batchExporting}>刷新</Button>
        </FilterGroup>
        <Space>
          {batchExporting ? (
            <div style={{ width: 200 }}>
              <Progress percent={exportProgress} size="small" status="active" />
            </div>
          ) : (
            <Button 
              icon={<ExportOutlined />} 
              onClick={handleBatchExport}
              disabled={selectedRowKeys.length === 0}
            >
              批量导出 {selectedRowKeys.length > 0 && `(${selectedRowKeys.length})`}
            </Button>
          )}
          <Button type="primary" icon={<PlusOutlined />} onClick={onCreate} disabled={batchExporting}>新建对账单</Button>
        </Space>
      </Toolbar>
      
      <Card styles={{ body: { padding: 0 } }} variant="borderless">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={filteredData}
          loading={loading}
          scroll={{ x: 1200 }}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
            getCheckboxProps: () => ({
              disabled: batchExporting,
            }),
          }}
          pagination={{
            defaultPageSize: 20,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </Card>
    </Container>
  );
};
