import React, { useState, useEffect, useCallback } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Select, Radio, Card, Tag, Row, Col, Space, Popconfirm, App } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, StopOutlined, CheckCircleOutlined } from '@ant-design/icons';
import axios from 'axios';
import styled from 'styled-components';
import { apiUrl } from '../lib/api';
import type { ColumnsType } from 'antd/es/table';

const Container = styled.div`
  padding: 24px;
`;

const Header = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
`;

const StyledCard = styled(Card)`
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
`;

const BatchToolbar = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 6px;
`;

interface BillingItem {
  id: number;
  name: string;
  level: string;
  unit: string;
  price: number;
  billing_mode: string;
  pick_priority: number;
  require_business_data: boolean;
  category: string;
  billing_note: string;
  status: string;
}

export default function BillingConfigPage() {
  const [items, setItems] = useState<BillingItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isBatchModalOpen, setIsBatchModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<BillingItem | null>(null);
  const [form] = Form.useForm();
  const [batchForm] = Form.useForm();
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchAction, setBatchAction] = useState<'price' | 'billing_mode' | null>(null);
  const { message } = App.useApp();

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(apiUrl('/settings/billing-items'), {
        params: { include_inactive: true }
      });
      setItems(res.data);
    } catch (e: any) {
      console.error(e);
      message.error('加载计费项失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const handleAdd = () => {
    setEditingItem(null);
    form.resetFields();
    form.setFieldsValue({
      level: 'L2',
      unit: '元/次',
      billing_mode: '智能择取',
      require_business_data: true,
      pick_priority: 50,
      status: '启用'
    });
    setIsModalOpen(true);
  };

  const handleEdit = (item: BillingItem) => {
    setEditingItem(item);
    form.setFieldsValue(item);
    setIsModalOpen(true);
  };

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        ...values,
        price: Number(values.price),
        pick_priority: Number(values.pick_priority),
      };

      if (editingItem) {
        await axios.put(apiUrl(`/settings/billing-items/${editingItem.id}`), payload);
        message.success('更新成功');
      } else {
        await axios.post(apiUrl('/settings/billing-items'), payload);
        message.success('创建成功');
      }
      setIsModalOpen(false);
      loadItems();
    } catch (e) {
      console.error(e);
      message.error('操作失败');
    }
  };

  const handleDeactivate = async (id: number) => {
    try {
      await axios.post(apiUrl(`/settings/billing-items/${id}/deactivate`));
      message.success('停用成功');
      loadItems();
    } catch (e) {
      message.error('停用失败');
    }
  };

  const handleActivate = async (id: number) => {
    try {
      await axios.post(apiUrl(`/settings/billing-items/${id}/activate`));
      message.success('启用成功');
      loadItems();
    } catch (e) {
      message.error('启用失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await axios.delete(apiUrl(`/settings/billing-items/${id}`));
      message.success('删除成功');
      loadItems();
    } catch (e) {
      message.error('删除失败');
    }
  };

  const handleBatchAction = (action: 'price' | 'billing_mode') => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要操作的计费项');
      return;
    }
    setBatchAction(action);
    batchForm.resetFields();
    setIsBatchModalOpen(true);
  };

  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要删除的计费项');
      return;
    }
    try {
      await axios.post(apiUrl('/settings/billing-items/batch/delete'), {
        item_ids: selectedRowKeys
      });
      message.success(`成功删除 ${selectedRowKeys.length} 个计费项`);
      setSelectedRowKeys([]);
      loadItems();
    } catch (e) {
      message.error('批量删除失败');
    }
  };

  const handleBatchOk = async () => {
    try {
      const values = await batchForm.validateFields();
      const updates: any = {};
      
      if (batchAction === 'price') {
        updates.price = Number(values.price);
      } else if (batchAction === 'billing_mode') {
        updates.billing_mode = values.billing_mode;
      }

      await axios.post(apiUrl('/settings/billing-items/batch/update'), {
        item_ids: selectedRowKeys,
        updates
      });

      message.success(`成功更新 ${selectedRowKeys.length} 个计费项`);
      setIsBatchModalOpen(false);
      setSelectedRowKeys([]);
      loadItems();
    } catch (e) {
      console.error(e);
      message.error('批量更新失败');
    }
  };

  const getDefaultPriority = (level: string) => {
    const defaults: Record<string, number> = { L1: 10, L2: 50, L3: 100, L4: 200 };
    return defaults[level] || 100;
  };

  const handleLevelChange = (level: string) => {
    form.setFieldsValue({ pick_priority: getDefaultPriority(level) });
  };

  const columns: ColumnsType<BillingItem> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '层级', dataIndex: 'level', key: 'level', render: (text: string) => <Tag>{text}</Tag> },
    { title: '单价', dataIndex: 'price', key: 'price', render: (val: number) => `¥${val}` },
    { title: '单位', dataIndex: 'unit', key: 'unit' },
    { title: '计费模式', dataIndex: 'billing_mode', key: 'billing_mode', render: (mode: string) => {
      const colors: Record<string, string> = {
        '固定入账': 'blue',
        '智能择取': 'green',
        '模拟填充': 'orange'
      };
      return <Tag color={colors[mode] || 'default'}>{mode}</Tag>;
    }},
    { title: '优先级', dataIndex: 'pick_priority', key: 'pick_priority' },
    { title: '分类', dataIndex: 'category', key: 'category' },
    { 
      title: '状态', 
      dataIndex: 'status', 
      key: 'status',
      render: (status: string) => (
        <Tag color={status === '启用' ? 'success' : 'default'}>{status}</Tag>
      )
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: BillingItem) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          {record.status === '启用' ? (
            <Button type="link" size="small" icon={<StopOutlined />} onClick={() => handleDeactivate(record.id)}>
              停用
            </Button>
          ) : (
            <Button type="link" size="small" icon={<CheckCircleOutlined />} onClick={() => handleActivate(record.id)}>
              启用
            </Button>
          )}
          <Popconfirm
            title="确定删除此计费项？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    },
  };

  return (
    <Container>
      <Header>
        <h2 style={{ fontSize: 24, fontWeight: 'bold' }}>计费项配置</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          新增计费项
        </Button>
      </Header>

      {selectedRowKeys.length > 0 && (
        <BatchToolbar>
          <span>已选择 <strong>{selectedRowKeys.length}</strong> 项</span>
          <Space>
            <Button size="small" onClick={() => handleBatchAction('price')}>
              批量修改单价
            </Button>
            <Button size="small" onClick={() => handleBatchAction('billing_mode')}>
              批量修改计费模式
            </Button>
            <Popconfirm
              title={`确定删除选中的 ${selectedRowKeys.length} 个计费项？`}
              onConfirm={handleBatchDelete}
              okText="确定"
              cancelText="取消"
            >
              <Button size="small" danger>
                批量删除
              </Button>
            </Popconfirm>
            <Button size="small" onClick={() => setSelectedRowKeys([])}>
              取消选择
            </Button>
          </Space>
        </BatchToolbar>
      )}

      <StyledCard>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          rowSelection={rowSelection}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </StyledCard>

      {/* 新增/编辑弹窗 */}
      <Modal
        title={editingItem ? "编辑计费项" : "新增计费项"}
        open={isModalOpen}
        onOk={handleOk}
        onCancel={() => setIsModalOpen(false)}
        width={800}
        zIndex={10}
        centered
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="计费项名称" rules={[{ required: true, message: '请输入名称' }]}>
                <Input placeholder="请输入名称" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="category" label="分类">
                <Input placeholder="例如：基础服务" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="price" label="单价" rules={[{ required: true, message: '请输入单价' }]}>
                <InputNumber style={{ width: '100%' }} prefix="¥" min={0} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="unit" label="单位" rules={[{ required: true }]}>
                <Select>
                  <Select.Option value="元/次">元/次</Select.Option>
                  <Select.Option value="元/月">元/月</Select.Option>
                  <Select.Option value="元/GB">元/GB</Select.Option>
                  <Select.Option value="元/人天">元/人天</Select.Option>
                  <Select.Option value="元/小时">元/小时</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="level" label="层级">
                <Select onChange={handleLevelChange}>
                  <Select.Option value="L1">L1 (最高)</Select.Option>
                  <Select.Option value="L2">L2</Select.Option>
                  <Select.Option value="L3">L3</Select.Option>
                  <Select.Option value="L4">L4 (最低)</Select.Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="pick_priority" label="优先级">
                <InputNumber style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="status" label="状态">
                <Select>
                  <Select.Option value="启用">启用</Select.Option>
                  <Select.Option value="停用">停用</Select.Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="billing_mode" label="计费模式" rules={[{ required: true }]}>
            <Radio.Group buttonStyle="solid">
              <Radio.Button value="固定入账">固定入账</Radio.Button>
              <Radio.Button value="智能择取">智能择取</Radio.Button>
              <Radio.Button value="模拟填充">模拟填充</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="billing_note" label="备注">
            <Input.TextArea rows={2} placeholder="计费项说明..." />
          </Form.Item>
        </Form>
      </Modal>

      {/* 批量操作弹窗 */}
      <Modal
        title={batchAction === 'price' ? '批量修改单价' : '批量修改计费模式'}
        open={isBatchModalOpen}
        onOk={handleBatchOk}
        onCancel={() => setIsBatchModalOpen(false)}
        width={500}
      >
        <Form form={batchForm} layout="vertical">
          <p style={{ marginBottom: 16, color: '#666' }}>
            即将修改 <strong>{selectedRowKeys.length}</strong> 个计费项
          </p>
          {batchAction === 'price' ? (
            <Form.Item 
              name="price" 
              label="新单价" 
              rules={[{ required: true, message: '请输入单价' }]}
            >
              <InputNumber style={{ width: '100%' }} prefix="¥" min={0} />
            </Form.Item>
          ) : (
            <Form.Item 
              name="billing_mode" 
              label="新计费模式" 
              rules={[{ required: true, message: '请选择计费模式' }]}
            >
              <Select>
                <Select.Option value="固定入账">固定入账</Select.Option>
                <Select.Option value="智能择取">智能择取</Select.Option>
                <Select.Option value="模拟填充">模拟填充</Select.Option>
              </Select>
            </Form.Item>
          )}
        </Form>
      </Modal>
    </Container>
  );
}
