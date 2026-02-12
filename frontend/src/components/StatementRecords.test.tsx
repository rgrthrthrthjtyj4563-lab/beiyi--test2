import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { StatementRecords } from './StatementRecords';
import axios from 'axios';

jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('StatementRecords', () => {
  const mockNavigate = jest.fn();
  const mockCreate = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders table and toolbar', () => {
    render(<StatementRecords onNavigate={mockNavigate} onCreate={mockCreate} />);
    expect(screen.getByText('新建对账单')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('搜索客户名称')).toBeInTheDocument();
  });

  it('loads and displays data', async () => {
    const mockData = [
      {
        id: '1',
        customer_name: 'Test Customer',
        statement_date: '2023-01',
        target_amount: 1000,
        actual_amount: 1000,
        is_match: true,
        export_status: 'pending',
        updated_at: '2023-01-01T12:00:00Z',
      },
    ];
    mockedAxios.get.mockResolvedValue({ data: mockData });

    render(<StatementRecords onNavigate={mockNavigate} onCreate={mockCreate} />);

    await waitFor(() => {
      expect(screen.getByText('Test Customer')).toBeInTheDocument();
      expect(screen.getByText('¥1,000.00')).toBeInTheDocument();
    });
  });

  it('calls onCreate when button clicked', () => {
    render(<StatementRecords onNavigate={mockNavigate} onCreate={mockCreate} />);
    fireEvent.click(screen.getByText('新建对账单'));
    expect(mockCreate).toHaveBeenCalled();
  });
});
