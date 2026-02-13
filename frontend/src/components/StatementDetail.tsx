import React, { useState, useEffect } from 'react';
import {
  Card,
  Descriptions,
  Table,
  Button,
  Tag,
  Space,
  Spin,
  Alert,
  Timeline,
  Statistic,
  Row,
  Col,
  Tooltip,
  App,
} from 'antd';
import {
  ArrowLeftOutlined,
  DownloadOutlined,
  FileTextOutlined,
  HistoryOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import styled from 'styled-components';
import { apiUrl } from '../lib/api';
import dayjs from 'dayjs';

const Container = styled.div`
  padding: 24px;
`;

const HeaderSection = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
`;

const TitleGroup = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
`;

const PageTitle = styled.h2`
  margin: 0;
  font-size: 20px;
  font-weight: 600;
`;

const StatsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
`;

const StatCard = styled(Card)<{ $color?: string }>`
  .ant-statistic-title {
    color: ${props => props.$color || 'inherit'};
    font-size: 14px;
  }
  .ant-statistic-content {
    color: ${props => props.$color || 'inherit'};
    font-size: 24px;
    font-weight: 600;
  }
`;

const LayerBadge = styled.div<{ $level: string }>`
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  background: ${props => {
    switch (props.$level) {
      case 'L1': return '#e6f7ff';
      case 'L2': return '#f6ffed';
      case 'L3': return '#fff7e6';
      case 'L4': return '#f9f0ff';
      default: return '#f5f5f5';
    }
  }};
  color: ${props => {
    switch (props.$level) {
      case 'L1': return '#1890ff';
      case 'L2': return '#52c41a';
      case 'L3': return '#fa8c16';
      case 'L4': return '#722ed1';
      default: return '#666';
    }
  }};
  border: 1px solid ${props => {
    switch (props.$level) {
      case 'L1': return '#91d5ff';
      case 'L2': return '#b7eb8f';
      case 'L3': return '#ffd591';
      case 'L4': return '#d3adf7';
      default: return '#d9d9d9';
    }
  }};
`;

const SourceTag = styled(Tag)<{ $source: string }>`
  ${props => {
    switch (props.$source) {
      case '业务真实数据':
        return 'background: #e6f7ff; border-color: #91d5ff; color: #1890ff;';
      case '择取计费':
        return 'background: #f6ffed; border-color: #b7eb8f; color: #52c41a;';
      case '规则分配':
        return 'background: #fff7e6; border-color: #ffd591; color: #fa8c16;';
      case '尾差调平':
        return 'background: #fff1f0; border-color: #ffa39e; color: #f5222d;';
      case '人工录入':
        return 'background: #f9f0ff; border-color: #d3adf7; color: #722ed1;';
      default:
        return '';
    }
  }}
`;

interface StatementItem {
  level: string;
  name: string;
  unit: string;
  price: number;
  quantity: number;
  amount: number;
  source: string;
  quantity_mode: string;
  actual_qty: number;
  billed_qty: number;
  unbilled_qty: number;
  decision_reason_code: string;
  category: string;
  billing_note: string;
}

interface StatementSummary {
  target_amount: number;
  generated_amount: number;
  diff: number;
  layers: Record<string, { amount: number; ratio: number }>;
  warnings: string[];
  calc_snapshot_json: Record<string, any>;
  item_decision_json: Record<string, any>[];
}

interface Statement {
  customer: string;
  period: string;
  target_amount: number;
  summary: StatementSummary;
  items: StatementItem[];
}

interface HistoryItem {
  timestamp: string;
  action: string;
  note: string;
}

interface StatementRecord {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  statement: Statement;
  history: HistoryItem[];
  rule_template_name?: string;
  rule_template_version?: number;
  rule_strategy_name?: string;
  engine_version?: string;
}

interface StatementDetailProps {
  statementId: string;
  onBack: () => void;
}

const levelLabels: Record<string, string> = {
  L1: 'L1 系统收费层',
  L2: 'L2 报告辅助加工',
  L3: 'L3 增值服务',
  L4: 'L4 其他服务',
};

export const StatementDetail: React.FC<StatementDetailProps> = ({
  statementId,
  onBack,
}) => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<StatementRecord | null>(null);
  const [exporting, setExporting] = useState(false);
  const { message } = App.useApp();

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await axios.get(apiUrl(`/statements/${statementId}`));
      setData(res.data);
    } catch (error) {
      console.error('Failed to fetch statement:', error);
      message.error('加载对账单详情失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  const handleExport = async () => {
    if (!data) return;
    setExporting(true);
    try {
      const res = await axios.post(
        apiUrl(`/statements/${statementId}/export`),
        {},
        { responseType: 'blob' }
      );
      
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `Statement of Account_${data.statement.customer}_${data.statement.period}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
      message.success('导出成功');
    } catch (error) {
      console.error('Export failed:', error);
      message.error('导出失败');
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <Container>
        <Spin size="large" tip="加载中...">
          <div style={{ minHeight: 400 }} />
        </Spin>
      </Container>
    );
  }

  if (!data) {
    return (
      <Container>
        <Alert
          message="加载失败"
          description="无法获取对账单详情，请返回重试"
          type="error"
          showIcon
          action={
            <Button onClick={onBack} icon={<ArrowLeftOutlined />}>
              返回列表
            </Button>
          }
        />
      </Container>
    );
  }

  const { statement, history, status } = data;
  const { summary, items } = statement;
  const diffPercent = summary.target_amount > 0
    ? (Math.abs(summary.diff) / summary.target_amount * 100).toFixed(2)
    : '0.00';

  const columns = [
    {
      title: '层级',
      dataIndex: 'level',
      key: 'level',
      width: 140,
      render: (level: string) => (
        <LayerBadge $level={level}>
          {levelLabels[level] || level}
        </LayerBadge>
      ),
    },
    {
      title: '计费项',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: StatementItem) => (
        <Space direction="vertical" size={0}>
          <span style={{ fontWeight: 500 }}>{name}</span>
          {record.category && (
            <span style={{ fontSize: 12, color: '#888' }}>
              分类: {record.category}
            </span>
          )}
        </Space>
      ),
    },
    {
      title: '单价',
      dataIndex: 'price',
      key: 'price',
      align: 'right' as const,
      width: 120,
      render: (price: number) => `¥${price.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right' as const,
      width: 100,
      render: (qty: number, record: StatementItem) => (
        <Tooltip title={
          <div>
            <div>实际数量: {record.actual_qty}</div>
            <div>计费数量: {record.billed_qty}</div>
            <div>
              {record.level === 'L1' && record.quantity_mode === 'ACTUAL_SELECTABLE'
                ? `折让条数（月度商议）: ${record.unbilled_qty}`
                : `未计费: ${record.unbilled_qty}`}
            </div>
          </div>
        }>
          <span>{qty}</span>
        </Tooltip>
      ),
    },
    {
      title: '单位',
      dataIndex: 'unit',
      key: 'unit',
      width: 80,
      render: (unit: string) => unit.split('/').pop() || unit,
    },
    {
      title: '金额',
      dataIndex: 'amount',
      key: 'amount',
      align: 'right' as const,
      width: 150,
      render: (amount: number) => (
        <span style={{ fontWeight: 600 }}>
          ¥{amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
        </span>
      ),
    },
    {
      title: '数据来源',
      dataIndex: 'source',
      key: 'source',
      width: 120,
      render: (source: string) => (
        <SourceTag $source={source}>{source}</SourceTag>
      ),
    },
    {
      title: '计费说明',
      dataIndex: 'billing_note',
      key: 'billing_note',
      ellipsis: true,
      render: (note: string) => note || '-',
    },
  ];

  const getActionIcon = (action: string) => {
    switch (action) {
      case 'CREATED':
        return <FileTextOutlined style={{ color: '#1890ff' }} />;
      case 'EXPORT':
        return <DownloadOutlined style={{ color: '#52c41a' }} />;
      default:
        return <InfoCircleOutlined />;
    }
  };

  const getActionLabel = (action: string) => {
    switch (action) {
      case 'CREATED':
        return '创建对账单';
      case 'EXPORT':
        return '导出文件';
      default:
        return action;
    }
  };

  return (
    <Container>
      <HeaderSection>
        <TitleGroup>
          <Button icon={<ArrowLeftOutlined />} onClick={onBack}>
            返回列表
          </Button>
          <PageTitle>
            <FileTextOutlined style={{ marginRight: 8 }} />
            对账单详情
          </PageTitle>
          <Tag color={status === 'EXPORTED' ? 'blue' : 'default'}>
            {status === 'EXPORTED' ? '已导出' : '草稿'}
          </Tag>
        </TitleGroup>
        <Space>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            loading={exporting}
            onClick={handleExport}
          >
            导出 Excel
          </Button>
        </Space>
      </HeaderSection>

      {summary.warnings && summary.warnings.length > 0 && (
        <Alert
          message="生成警告"
          description={
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {summary.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          }
          type="warning"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="客户名称"
              value={statement.customer}
              valueStyle={{ fontSize: 16 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="账期"
              value={statement.period}
              valueStyle={{ fontSize: 16 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="创建时间"
              value={dayjs(data.created_at).format('YYYY-MM-DD HH:mm')}
              valueStyle={{ fontSize: 14 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="更新时间"
              value={dayjs(data.updated_at).format('YYYY-MM-DD HH:mm')}
              valueStyle={{ fontSize: 14 }}
            />
          </Card>
        </Col>
      </Row>

      <StatsGrid>
        <StatCard>
          <Statistic
            title="目标金额"
            value={`¥${summary.target_amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`}
            prefix={<InfoCircleOutlined />}
          />
        </StatCard>
        <StatCard>
          <Statistic
            title="实际生成金额"
            value={`¥${summary.generated_amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`}
            prefix={
              Math.abs(summary.diff) < 0.01
                ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
                : <WarningOutlined style={{ color: '#fa8c16' }} />
            }
          />
        </StatCard>
        <StatCard $color={Math.abs(summary.diff) < 0.01 ? '#52c41a' : '#f5222d'}>
          <Statistic
            title="差额"
            value={`¥${summary.diff.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} (${diffPercent}%)`}
            valueStyle={{ color: Math.abs(summary.diff) < 0.01 ? '#52c41a' : '#f5222d' }}
            prefix={
              Math.abs(summary.diff) < 0.01
                ? <CheckCircleOutlined />
                : <CloseCircleOutlined />
            }
          />
        </StatCard>
      </StatsGrid>

      <Card title="分层统计" style={{ marginBottom: 24 }}>
        <Row gutter={[16, 16]}>
          {['L1', 'L2', 'L3', 'L4'].map((level) => {
            const layer = summary.layers[level];
            if (!layer) return null;
            return (
              <Col xs={24} sm={12} lg={6} key={level}>
                <Card size="small" bordered>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <LayerBadge $level={level}>{levelLabels[level]}</LayerBadge>
                    <span style={{ fontSize: 12, color: '#888' }}>
                      占比 {(layer.ratio * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div style={{ marginTop: 12, fontSize: 20, fontWeight: 600 }}>
                    ¥{layer.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                  </div>
                </Card>
              </Col>
            );
          })}
        </Row>
      </Card>

      <Card 
        title={
          <Space>
            <FileTextOutlined />
            <span>计费明细</span>
            <Tag>{items.length} 项</Tag>
          </Space>
        }
        style={{ marginBottom: 24 }}
      >
        <Table
          columns={columns}
          dataSource={items}
          rowKey={(record, index) => `${record.name}-${index}`}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (total) => `共 ${total} 项`,
          }}
          scroll={{ x: 1200 }}
          summary={() => (
            <Table.Summary fixed>
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={5}>
                  <span style={{ fontWeight: 600 }}>合计</span>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={1} align="right">
                  <span style={{ fontWeight: 600 }}>
                    ¥{summary.generated_amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                  </span>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={2} colSpan={2} />
              </Table.Summary.Row>
            </Table.Summary>
          )}
        />
      </Card>

      <Card
        title={
          <Space>
            <HistoryOutlined />
            <span>操作历史</span>
          </Space>
        }
      >
        <Timeline
          mode="left"
          items={history.map((h) => ({
            dot: getActionIcon(h.action),
            label: dayjs(h.timestamp).format('YYYY-MM-DD HH:mm:ss'),
            children: (
              <div>
                <div style={{ fontWeight: 500 }}>{getActionLabel(h.action)}</div>
                {h.note && <div style={{ color: '#888', fontSize: 12 }}>{h.note}</div>}
              </div>
            ),
          }))}
        />
      </Card>
    </Container>
  );
};

export default StatementDetail;
