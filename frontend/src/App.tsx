import React, { useState, useEffect } from 'react';
import { Layout, Menu, ConfigProvider, theme, Button, App as AntdApp } from 'antd';
import { FileTextOutlined, SettingOutlined, MenuUnfoldOutlined, MenuFoldOutlined } from '@ant-design/icons';
import styled, { ThemeProvider } from 'styled-components';
import BillingConfigPage from './components/BillingConfigPage';
import { StatementRecords } from './components/StatementRecords';
import { CreateStatementModal } from './components/CreateStatementModal';
import { StatementDetail } from './components/StatementDetail';

const { Header, Sider, Content } = Layout;

const Logo = styled.div`
  height: 64px;
  padding: 16px;
  color: #1677ff;
  font-size: 18px;
  font-weight: bold;
  display: flex;
  align-items: center;
  white-space: nowrap;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.1);
`;

const AppContainer = styled(Layout)`
  min-height: 100vh;
`;

const App: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [currentView, setCurrentView] = useState('records');
  const [isDarkMode, setIsDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return false;
  });
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [currentStatementId, setCurrentStatementId] = useState<string | null>(null);
  const [recordsRefreshKey, setRecordsRefreshKey] = useState(0);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const match = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setIsDarkMode(e.matches);
    match.addEventListener('change', handler);
    return () => match.removeEventListener('change', handler);
  }, []);

  const items = [
    {
      key: 'records',
      icon: <FileTextOutlined />,
      label: '对账单记录',
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '系统设置',
    },
  ];

  const handleMenuClick = (e: { key: string }) => {
    setCurrentView(e.key);
    // If navigating away from detail, reset id
    setCurrentStatementId(null);
  };

  const renderContent = () => {
    if (currentStatementId) {
      return (
        <StatementDetail
          statementId={currentStatementId}
          onBack={() => setCurrentStatementId(null)}
        />
      );
    }

    switch (currentView) {
      case 'records':
        return (
          <StatementRecords 
            onNavigate={(id) => setCurrentStatementId(id)} 
            onCreate={() => setIsCreateModalOpen(true)}
            refreshKey={recordsRefreshKey}
          />
        );
      case 'settings':
        return <BillingConfigPage />;
      default:
        return null;
    }
  };

  return (
    <ConfigProvider
      theme={{
        algorithm: isDarkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
        },
      }}
    >
      <AntdApp>
        <ThemeProvider theme={{ mode: isDarkMode ? 'dark' : 'light' }}>
          <AppContainer>
            <Sider trigger={null} collapsible collapsed={collapsed} theme={isDarkMode ? 'dark' : 'light'}>
              <Logo>
                {collapsed ? '工具' : '对账单生成工具'}
              </Logo>
              <Menu
                theme={isDarkMode ? 'dark' : 'light'}
                mode="inline"
                selectedKeys={[currentView]}
                items={items}
                onClick={handleMenuClick}
              />
            </Sider>
            <Layout>
              <Header style={{ padding: 0, background: isDarkMode ? '#141414' : '#fff', display: 'flex', alignItems: 'center', paddingLeft: 16 }}>
                <Button
                  type="text"
                  icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                  onClick={() => setCollapsed(!collapsed)}
                  style={{
                    fontSize: '16px',
                    width: 64,
                    height: 64,
                  }}
                />
                <span style={{ fontSize: 18, fontWeight: 500, marginLeft: 16 }}>
                  {currentView === 'records' ? '对账单记录' : '系统设置'}
                </span>
              </Header>
              <Content
                style={{
                  margin: '24px 16px',
                  padding: 24,
                  minHeight: 280,
                  background: isDarkMode ? '#141414' : '#fff',
                  borderRadius: 8,
                  overflow: 'auto',
                }}
              >
                {renderContent()}
              </Content>
            </Layout>
          </AppContainer>
          
          <CreateStatementModal 
            open={isCreateModalOpen} 
            onCancel={() => setIsCreateModalOpen(false)} 
            onSuccess={() => {
              setIsCreateModalOpen(false);
              setRecordsRefreshKey((prev) => prev + 1);
            }} 
          />
        </ThemeProvider>
      </AntdApp>
    </ConfigProvider>
  );
};

export default App;
