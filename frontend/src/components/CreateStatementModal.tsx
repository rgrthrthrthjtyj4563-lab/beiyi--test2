import React, { useState } from 'react';
import { Modal, Form, Input, DatePicker, InputNumber, Button, Upload, App, Space } from 'antd';
import { InboxOutlined, DownloadOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import axios from 'axios';
import { apiUrl } from '../lib/api';
import dayjs from 'dayjs';

interface CreateStatementModalProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}

interface ParseResult {
  rows_total: number;
  rows_used: number;
  matched_columns: string[];
  unmatched_columns: string[];
  quantities: Record<string, number>;
}

export const CreateStatementModal: React.FC<CreateStatementModalProps> = ({ open, onCancel, onSuccess }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [checkingFeasibility, setCheckingFeasibility] = useState(false);
  const [feasibilityParseResult, setFeasibilityParseResult] = useState<ParseResult | null>(null);
  const { message } = App.useApp();

  const resolvePeriodString = (values?: any) => {
    const dateVal = values?.statement_date ?? form.getFieldValue('statement_date');
    if (!dateVal || typeof dateVal.format !== 'function') {
      return '';
    }
    return dateVal.format('YYYY-MM');
  };

  const normalizeTargetAmount = (raw: any) => {
    const num = Number(raw || 0);
    if (!Number.isFinite(num) || num <= 0) return 0;
    return Math.floor(num / 10) * 10;
  };

  const checkFeasibility = async (values: any) => {
    const period = resolvePeriodString(values);
    if (!period) {
      message.error('请选择对账日期');
      return null;
    }
    setCheckingFeasibility(true);
    try {
      const formData = new FormData();
      const normalizedTarget = normalizeTargetAmount(values.target_amount);
      formData.append('target_amount', String(normalizedTarget));
      formData.append('customer', values.customer_name);
      formData.append('period', period);
      
      // 始终传递文件，让后端决定是否需要解析
      if (fileList[0]?.originFileObj) {
        formData.append('file', fileList[0].originFileObj);
      }

      const response = await axios.post(apiUrl('/statements/feasibility'), formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 45000,
      });
      if (response.data.parse_result) {
        setFeasibilityParseResult(response.data.parse_result);
      }
      return response.data;
    } catch (e: any) {
      console.error('可行性检查失败:', e);
      const isTimeout = e?.code === 'ECONNABORTED' || e?.response?.status === 408;
      const errorMsg = isTimeout 
        ? '可行性检查超时，请稍后重试。如文件较大，解析可能需要更长时间。'
        : (e.response?.data?.detail || e.message || '未知错误');
      message.error('可行性检查失败: ' + errorMsg);
      if (isTimeout) {
        message.warning('请求超时，请检查网络或稍后重试');
      }
      return null;
    } finally {
      setCheckingFeasibility(false);
    }
  };

  const submitStatement = async (values: any, parseResult?: ParseResult | null) => {
    const period = resolvePeriodString(values);
    if (!period) {
      message.error('请选择对账日期');
      return;
    }

    try {
      const submitData = new FormData();
      submitData.append('customer', values.customer_name);
      submitData.append('period', period);
      const normalizedTarget = normalizeTargetAmount(values.target_amount);
      submitData.append('target_amount', String(normalizedTarget));
      
      if (parseResult) {
        submitData.append('preview_json', JSON.stringify(parseResult));
        // 有预览数据时不再发送文件，避免重复解析
      } else if (fileList.length > 0 && fileList[0].originFileObj) {
        submitData.append('file', fileList[0].originFileObj);
      }

      await axios.post(apiUrl('/statements'), submitData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 120000, // 增加到120秒，确保大文件有足够时间
      });
    } catch (e: any) {
      console.error(e);
      const isTimeout = e?.code === 'ECONNABORTED' || e?.response?.status === 408;
      const errorMsg = isTimeout
        ? '创建超时，请稍后重试。如文件较大，处理可能需要更长时间。'
        : (e.response?.data?.detail || '未知错误');
      message.error('创建失败: ' + errorMsg);
    }
  };

  const handleImport = async () => {
    try {
      const values = await form.validateFields();
      if (fileList.length === 0) {
        message.error('请上传业务明细文件');
        return;
      }
      setLoading(true);
      const feasibility = await checkFeasibility(values);
      if (!feasibility?.feasible) {
        const errorMsg = feasibility?.message || feasibility?.reason_code || feasibility?.reason || '当前配置无法生成对账单，请调整参数后重试';
        message.error(errorMsg);
        return;
      }
      if (feasibility?.lightweight_hint && !feasibility.lightweight_hint.feasible) {
        const hintMsg = feasibility.lightweight_hint.message || '业务数据不足，将依赖模拟项补齐';
        message.warning(hintMsg);
      }
      const parseResult = feasibility?.parse_result || feasibilityParseResult;
      await submitStatement(values, parseResult);
      message.success('导入成功');
      setTimeout(() => {
        onSuccess();
        reset();
      }, 1200);
    } catch (e) {
      // validation failed
    } finally {
      setLoading(false);
    }
  };

  const downloadTemplate = async () => {
    const hideLoading = message.loading('正在生成模板...', 0);
    try {
      console.log('开始下载模板，请求地址:', apiUrl('/templates/input/download'));
      
      const response = await axios.get(apiUrl('/templates/input/download'), {
        responseType: 'blob',
        timeout: 10000, // 10秒超时
      });
      
      console.log('模板下载响应:', {
        status: response.status,
        contentType: response.headers['content-type'],
        size: response.data?.size || response.data?.length,
      });
      
      // 检查响应是否为错误（如果出错，后端可能返回 JSON 而非 blob）
      if (response.data?.type === 'application/json') {
        const reader = new FileReader();
        reader.onload = () => {
          try {
            const error = JSON.parse(reader.result as string);
            message.error(error.detail || '模板生成失败');
          } catch {
            message.error('模板生成失败');
          }
        };
        reader.readAsText(response.data);
        return;
      }
      
      // 创建下载链接
      const blob = new Blob([response.data], { 
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = '业务数据输入模板.xlsx';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
      message.success('模板下载成功！请在下载文件夹中查看"业务数据输入模板.xlsx"');
    } catch (error: any) {
      console.error('模板下载失败:', error);
      
      if (error.response) {
        // 服务器返回错误
        console.error('服务器错误:', error.response.status, error.response.data);
        if (error.response.data instanceof Blob) {
          // 尝试读取错误信息
          const reader = new FileReader();
          reader.onload = () => {
            try {
              const errorData = JSON.parse(reader.result as string);
              message.error(`下载失败: ${errorData.detail || '服务器错误'}`);
            } catch {
              message.error('模板下载失败，服务器返回错误');
            }
          };
          reader.readAsText(error.response.data);
        } else {
          message.error(`下载失败: ${error.response.data?.detail || '服务器错误'}`);
        }
      } else if (error.request) {
        // 请求发送但没有收到响应
        message.error('下载失败: 无法连接到服务器，请检查网络');
      } else {
        // 请求配置出错
        message.error(`下载失败: ${error.message || '未知错误'}`);
      }
    } finally {
      hideLoading();
    }
  };

  const reset = () => {
    form.resetFields();
    setFileList([]);
    setFeasibilityParseResult(null);
  };

  const handleCancel = () => {
    reset();
    onCancel();
  };

  const handleFileChange = (info: any) => {
    const { fileList: newFileList } = info;
    setFileList(newFileList);
  };

  return (
    <Modal
      open={open}
      title="新建对账单"
      onCancel={handleCancel}
      footer={
        <Space style={{ marginTop: 12 }}>
          <Button onClick={handleCancel}>取消</Button>
          <Button type="primary" onClick={handleImport} loading={loading || checkingFeasibility}>
            导入
          </Button>
        </Space>
      }
      width={560}
    >
      <Form form={form} layout="vertical" initialValues={{ statement_date: dayjs() }}>
        <Form.Item name="customer_name" label="客户名称" rules={[{ required: true, message: '请输入客户名称' }]}>
          <Input placeholder="请输入客户名称" />
        </Form.Item>
        <Form.Item name="statement_date" label="对账日期" rules={[{ required: true, message: '请选择对账日期' }]}>
          <DatePicker picker="month" style={{ width: '100%' }} placeholder="请选择对账日期" />
        </Form.Item>
        <Form.Item
          name="target_amount"
          label="目标金额"
          rules={[
            { required: true, message: '请输入目标金额' },
            {
              validator: (_, value) => {
                const num = Number(value);
                if (!Number.isFinite(num) || num <= 0) return Promise.reject(new Error('目标金额必须大于0'));
                if (num % 10 !== 0) return Promise.reject(new Error('目标金额必须为10元整数倍'));
                return Promise.resolve();
              },
            },
          ]}
        >
          <InputNumber
            style={{ width: '100%' }}
            prefix="¥"
            min={10}
            step={10}
            precision={0}
            formatter={value => `${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
            parser={value => value!.replace(/\$\s?|(,*)/g, '')}
          />
        </Form.Item>
        <Form.Item label="模板下载">
          <Button type="primary" icon={<DownloadOutlined />} onClick={downloadTemplate}>
            下载模板
          </Button>
        </Form.Item>
        <Form.Item label="业务明细表" required>
          <Upload.Dragger
            fileList={fileList}
            beforeUpload={() => false}
            onChange={handleFileChange}
            maxCount={1}
            accept=".xlsx,.xls,.csv"
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
            <p className="ant-upload-hint">支持 Excel (.xlsx, .xls) 或 CSV 格式</p>
          </Upload.Dragger>
        </Form.Item>
      </Form>
    </Modal>
  );
};
