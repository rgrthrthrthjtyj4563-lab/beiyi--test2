import { useState, useEffect } from 'react'
import axios from 'axios'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import StatementDetail from './components/StatementDetail'

const API_URL = 'http://localhost:8000'

// Utility for class names
function cn(...inputs) {
  return twMerge(clsx(inputs))
}

function App() {
  const [view, setView] = useState('settings') // settings, dashboard, create, detail
  const [currentId, setCurrentId] = useState(null)

  return (
    <div className="min-h-screen bg-gray-50 flex font-sans text-gray-900">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 fixed h-full z-10 hidden md:block">
        <div className="p-6 border-b border-gray-200">
          <h1 className="text-xl font-bold text-blue-600 flex items-center gap-2">
            <span>对账单生成系统</span>
          </h1>
        </div>
        <nav className="p-4 space-y-1">
          <NavItem active={view === 'settings'} onClick={() => setView('settings')}>系统设置</NavItem>
          <NavItem active={view === 'dashboard'} onClick={() => setView('dashboard')}>仪表盘</NavItem>
          <NavItem active={view === 'create'} onClick={() => setView('create')}>新建对账单</NavItem>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 md:ml-64 p-8">
        {view === 'settings' && <BillingConfigPage />}
        {view === 'dashboard' && <Dashboard onNavigate={(id) => { setCurrentId(id); setView('detail') }} onCreate={() => setView('create')} />}
        {view === 'create' && <CreateStatement onCancel={() => setView('dashboard')} onSuccess={() => setView('dashboard')} />}
        {view === 'detail' && <StatementDetail id={currentId} onBack={() => setView('dashboard')} />}
      </main>
    </div>
  )
}

function NavItem({ children, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left px-4 py-2 rounded-md text-sm font-medium transition-colors",
        active ? "bg-blue-50 text-blue-700" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
      )}
    >
      {children}
    </button>
  )
}

function Dashboard({ onNavigate, onCreate }) {
  const [statements, setStatements] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStatements()
  }, [])

  const loadStatements = async () => {
    try {
      const res = await axios.get(`${API_URL}/statements`)
      setStatements(res.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">仪表盘</h2>
        <button onClick={onCreate} className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 shadow-sm transition-all">
          + 新建对账单
        </button>
      </div>

      <div className="bg-white shadow rounded-lg overflow-hidden border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">客户名称</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">账期</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">目标金额</th>
              <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">更新时间</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {statements.map(s => (
              <tr key={s.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => onNavigate(s.id)}>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{s.statement.customer}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{s.statement.period}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">¥{s.statement.target_amount.toLocaleString()}</td>
                <td className="px-6 py-4 whitespace-nowrap text-center">
                  <StatusBadge status={s.status} />
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">{new Date(s.updated_at).toLocaleDateString()}</td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium text-blue-600 hover:text-blue-900">查看详情</td>
              </tr>
            ))}
            {statements.length === 0 && !loading && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-gray-500">暂无数据，请点击新建。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BillingConfigPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [ruleLoading, setRuleLoading] = useState(true)
  const [ruleSaving, setRuleSaving] = useState(false)
  const [ruleVersions, setRuleVersions] = useState([])
  const [strategies, setStrategies] = useState([])
  const [formData, setFormData] = useState({
    code: '',
    name: '',
    level: 'L1',
    category: '',
    unit: '元/次',
    price: '',
    is_existing: false,
    can_simulate: false,
    must_use: false,
    billing_note: ''
  })
  const [ruleForm, setRuleForm] = useState({
    template_name: 'standard',
    strategy_name: 'equal_split_v1',
    ratios: { L1: 0.55, L2: 0.30, L3: 0.10, L4: 0.05 },
    l4_max_ratio: 0.05,
    ratio_warning_threshold: 0.15,
    fill_order_text: 'L2,L3,L4',
    version: 1
  })

  const loadItems = async () => {
    setLoading(true)
    try {
      const res = await axios.get(`${API_URL}/settings/billing-items`, {
        params: { include_inactive: true }
      })
      setItems(res.data)
    } catch (e) {
      alert('加载计费项失败')
    } finally {
      setLoading(false)
    }
  }

  const loadRules = async () => {
    setRuleLoading(true)
    try {
      const [ruleRes, versionRes, strategyRes] = await Promise.all([
        axios.get(`${API_URL}/settings/allocation-rules`, { params: { template_name: 'standard' } }),
        axios.get(`${API_URL}/settings/allocation-rules/versions`, { params: { template_name: 'standard', limit: 20 } }),
        axios.get(`${API_URL}/settings/allocation-strategies`)
      ])
      const rule = ruleRes.data || {}
      setRuleForm({
        template_name: rule.template_name || 'standard',
        strategy_name: rule.strategy_name || 'equal_split_v1',
        ratios: {
          L1: Number(rule?.ratios?.L1 || 0),
          L2: Number(rule?.ratios?.L2 || 0),
          L3: Number(rule?.ratios?.L3 || 0),
          L4: Number(rule?.ratios?.L4 || 0)
        },
        l4_max_ratio: Number(rule.l4_max_ratio || 0),
        ratio_warning_threshold: Number(rule.ratio_warning_threshold || 0),
        fill_order_text: (rule.fill_order || ['L2', 'L3', 'L4']).join(','),
        version: Number(rule.version || 1)
      })
      setRuleVersions(versionRes.data || [])
      setStrategies(strategyRes.data || [])
    } catch (e) {
      alert('加载规则配置失败')
    } finally {
      setRuleLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
    loadRules()
  }, [])

  const submitForm = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await axios.post(`${API_URL}/settings/billing-items`, {
        ...formData,
        price: Number(formData.price || 0)
      })
      setFormData({
        code: '',
        name: '',
        level: 'L1',
        category: '',
        unit: '元/次',
        price: '',
        is_existing: false,
        can_simulate: false,
        must_use: false,
        billing_note: ''
      })
      await loadItems()
    } catch (e) {
      alert('新增失败: ' + (e.response?.data?.detail || e.message))
    } finally {
      setSaving(false)
    }
  }

  const deactivateItem = async (id) => {
    if (!confirm('确认停用该计费项吗？')) return
    try {
      await axios.post(`${API_URL}/settings/billing-items/${id}/deactivate`)
      loadItems()
    } catch (e) {
      alert('停用失败')
    }
  }

  const toggleFlag = async (item, key) => {
    try {
      await axios.put(`${API_URL}/settings/billing-items/${item.id}`, {
        [key]: !item[key]
      })
      loadItems()
    } catch (e) {
      alert('更新失败')
    }
  }

  const editTemplateMeta = async (item) => {
    const category = prompt('计费分类', item.category || '')
    if (category === null) return
    const billingNote = prompt('计费说明', item.billing_note || '')
    if (billingNote === null) return
    try {
      await axios.put(`${API_URL}/settings/billing-items/${item.id}`, {
        category,
        billing_note: billingNote
      })
      loadItems()
    } catch (e) {
      alert('更新模板字段失败')
    }
  }

  const submitRule = async (e) => {
    e.preventDefault()
    setRuleSaving(true)
    try {
      const fillOrder = ruleForm.fill_order_text
        .split(',')
        .map(x => x.trim().toUpperCase())
        .filter(x => ['L1', 'L2', 'L3', 'L4'].includes(x))

      const payload = {
        template_name: ruleForm.template_name,
        strategy_name: ruleForm.strategy_name,
        ratios: {
          L1: Number(ruleForm.ratios.L1 || 0),
          L2: Number(ruleForm.ratios.L2 || 0),
          L3: Number(ruleForm.ratios.L3 || 0),
          L4: Number(ruleForm.ratios.L4 || 0)
        },
        l4_max_ratio: Number(ruleForm.l4_max_ratio || 0),
        ratio_warning_threshold: Number(ruleForm.ratio_warning_threshold || 0),
        fill_order: fillOrder.length > 0 ? fillOrder : ['L2', 'L3', 'L4']
      }

      await axios.put(`${API_URL}/settings/allocation-rules`, payload)
      await loadRules()
      alert('规则模板已保存并生成新版本快照')
    } catch (e) {
      alert('保存规则失败: ' + (e.response?.data?.detail || e.message))
    } finally {
      setRuleSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">系统设置 / 计费项配置</h2>
        <p className="text-sm text-gray-600 mt-1">先维护计费项与规则，再进入对账单生成。</p>
      </div>

      <form onSubmit={submitForm} className="bg-white shadow rounded-lg p-6 border border-gray-200 space-y-4">
        <h3 className="text-lg font-semibold">新增计费项</h3>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <input
            className="border rounded-md p-2"
            placeholder="编码(可选)"
            value={formData.code}
            onChange={e => setFormData({ ...formData, code: e.target.value })}
          />
          <input
            required
            className="border rounded-md p-2 md:col-span-2"
            placeholder="计费项名称"
            value={formData.name}
            onChange={e => setFormData({ ...formData, name: e.target.value })}
          />
          <input
            className="border rounded-md p-2"
            placeholder="计费分类"
            value={formData.category}
            onChange={e => setFormData({ ...formData, category: e.target.value })}
          />
          <select
            className="border rounded-md p-2"
            value={formData.level}
            onChange={e => setFormData({ ...formData, level: e.target.value })}
          >
            <option value="L1">L1</option>
            <option value="L2">L2</option>
            <option value="L3">L3</option>
            <option value="L4">L4</option>
          </select>
          <input
            required
            className="border rounded-md p-2"
            placeholder="单位"
            value={formData.unit}
            onChange={e => setFormData({ ...formData, unit: e.target.value })}
          />
          <input
            required
            type="number"
            step="0.01"
            min="0"
            className="border rounded-md p-2"
            placeholder="单价"
            value={formData.price}
            onChange={e => setFormData({ ...formData, price: e.target.value })}
          />
        </div>
        <div>
          <input
            className="border rounded-md p-2 w-full"
            placeholder="计费说明（用于导出模板的“计费说明”列）"
            value={formData.billing_note}
            onChange={e => setFormData({ ...formData, billing_note: e.target.value })}
          />
        </div>

        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={formData.is_existing} onChange={e => setFormData({ ...formData, is_existing: e.target.checked })} />
            现有业务项
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={formData.can_simulate} onChange={e => setFormData({ ...formData, can_simulate: e.target.checked })} />
            允许模拟
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={formData.must_use} onChange={e => setFormData({ ...formData, must_use: e.target.checked })} />
            必须项
          </label>
        </div>

        <div>
          <button type="submit" disabled={saving} className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50">
            {saving ? '保存中...' : '新增计费项'}
          </button>
        </div>
      </form>

      <form onSubmit={submitRule} className="bg-white shadow rounded-lg p-6 border border-gray-200 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">分配规则模板（standard）</h3>
            <p className="text-xs text-gray-500 mt-1">支持策略切换与版本快照，保存后会自动生成新版本。</p>
          </div>
          <div className="text-right text-sm">
            <div className="text-gray-500">当前版本</div>
            <div className="font-semibold text-gray-900">v{ruleForm.version || '-'}</div>
          </div>
        </div>

        {ruleLoading ? (
          <div className="text-sm text-gray-500">规则加载中...</div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label className="text-sm">
                <div className="mb-1 text-gray-700">策略</div>
                <select
                  className="border rounded-md p-2 w-full"
                  value={ruleForm.strategy_name}
                  onChange={e => setRuleForm({ ...ruleForm, strategy_name: e.target.value })}
                >
                  {(strategies.length > 0 ? strategies : [{ key: 'equal_split_v1', label: '等额分摊策略' }]).map(s => (
                    <option key={s.key} value={s.key}>{s.label}</option>
                  ))}
                </select>
              </label>
              <label className="text-sm">
                <div className="mb-1 text-gray-700">L4 上限比例</div>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  className="border rounded-md p-2 w-full"
                  value={ruleForm.l4_max_ratio}
                  onChange={e => setRuleForm({ ...ruleForm, l4_max_ratio: e.target.value })}
                />
              </label>
              <label className="text-sm">
                <div className="mb-1 text-gray-700">占比告警阈值</div>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  className="border rounded-md p-2 w-full"
                  value={ruleForm.ratio_warning_threshold}
                  onChange={e => setRuleForm({ ...ruleForm, ratio_warning_threshold: e.target.value })}
                />
              </label>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {['L1', 'L2', 'L3', 'L4'].map(level => (
                <label key={level} className="text-sm">
                  <div className="mb-1 text-gray-700">{level} 比例</div>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    className="border rounded-md p-2 w-full"
                    value={ruleForm.ratios[level]}
                    onChange={e => setRuleForm({
                      ...ruleForm,
                      ratios: { ...ruleForm.ratios, [level]: e.target.value }
                    })}
                  />
                </label>
              ))}
            </div>

            <label className="text-sm block">
              <div className="mb-1 text-gray-700">补齐顺序（逗号分隔）</div>
              <input
                className="border rounded-md p-2 w-full"
                value={ruleForm.fill_order_text}
                onChange={e => setRuleForm({ ...ruleForm, fill_order_text: e.target.value })}
                placeholder="例如：L2,L3,L4"
              />
            </label>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={ruleSaving}
                className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {ruleSaving ? '保存中...' : '保存规则并生成版本'}
              </button>
            </div>
          </>
        )}
      </form>

      <div className="bg-white shadow rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold">规则版本快照</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">版本</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">策略</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">比例</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">补齐顺序</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">创建时间</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {ruleVersions.map(v => (
                <tr key={`${v.template_name}-${v.version}`}>
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">v{v.version}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">{v.strategy_name}</td>
                  <td className="px-4 py-3 text-xs text-gray-600">
                    L1 {Number(v?.ratios?.L1 || 0).toFixed(2)} /
                    L2 {Number(v?.ratios?.L2 || 0).toFixed(2)} /
                    L3 {Number(v?.ratios?.L3 || 0).toFixed(2)} /
                    L4 {Number(v?.ratios?.L4 || 0).toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{(v.fill_order || []).join(', ')}</td>
                  <td className="px-4 py-3 text-sm text-gray-500 text-right">{new Date(v.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {!ruleLoading && ruleVersions.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center px-6 py-10 text-gray-500">暂无规则快照</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white shadow rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold">计费项列表</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">名称</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">层级</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">分类</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">单价</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">状态</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">标记</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">计费说明</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">操作</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {items.map(item => (
                <tr key={item.id}>
                  <td className="px-4 py-3 text-sm">{item.name}</td>
                  <td className="px-4 py-3 text-sm">{item.level}</td>
                  <td className="px-4 py-3 text-sm">{item.category || '-'}</td>
                  <td className="px-4 py-3 text-sm text-right">{Number(item.price).toFixed(2)}</td>
                  <td className="px-4 py-3 text-sm">
                    <span className={cn(
                      "px-2 py-0.5 rounded-full text-xs font-medium",
                      item.status === 'ACTIVE' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'
                    )}>
                      {item.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-600">
                    <div className="flex flex-wrap gap-2">
                      <button onClick={() => toggleFlag(item, 'is_existing')} className="underline">现有:{item.is_existing ? 'Y' : 'N'}</button>
                      <button onClick={() => toggleFlag(item, 'can_simulate')} className="underline">模拟:{item.can_simulate ? 'Y' : 'N'}</button>
                      <button onClick={() => toggleFlag(item, 'must_use')} className="underline">必须:{item.must_use ? 'Y' : 'N'}</button>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-600 max-w-sm truncate" title={item.billing_note || ''}>
                    {item.billing_note || '-'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => editTemplateMeta(item)} className="text-blue-600 hover:text-blue-800 text-sm mr-3">编辑模板字段</button>
                    {item.status === 'ACTIVE' && (
                      <button onClick={() => deactivateItem(item.id)} className="text-red-600 hover:text-red-800 text-sm">停用</button>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center px-6 py-10 text-gray-500">暂无计费项</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status }) {
  const styles = {
    DRAFT: "bg-gray-100 text-gray-800",
    EXPORTED: "bg-green-100 text-green-800"
  }
  
  const labels = {
    DRAFT: "草稿",
    EXPORTED: "已导出"
  }

  return (
    <span className={cn("px-2.5 py-0.5 rounded-full text-xs font-medium", styles[status] || styles.DRAFT)}>
      {labels[status] || status}
    </span>
  )
}

function CreateStatement({ onCancel, onSuccess }) {
  const [formData, setFormData] = useState({
    target_amount: '',
    customer: '',
    period: '',
    no_data_reason: ''
  })
  const [step, setStep] = useState(1)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [mappingSaving, setMappingSaving] = useState(false)
  const [templateName] = useState('default')
  const [fieldMappings, setFieldMappings] = useState({})
  const [billingItemNames, setBillingItemNames] = useState([])

  useEffect(() => {
    const loadInitData = async () => {
      try {
        const [configRes, mappingRes] = await Promise.all([
          axios.get(`${API_URL}/config`),
          axios.get(`${API_URL}/settings/field-mappings`, { params: { template_name: templateName } })
        ])
        setBillingItemNames((configRes.data || []).map(i => i.name))
        setFieldMappings(mappingRes.data?.mappings || {})
      } catch (e) {
        console.error(e)
      }
    }
    loadInitData()
  }, [templateName])

  const parsePreview = async () => {
    if (!file) {
      setPreview(null)
      return null
    }
    setPreviewLoading(true)
    try {
      const data = new FormData()
      data.append('period', formData.period)
      data.append('template_name', templateName)
      data.append('mappings_json', JSON.stringify(fieldMappings))
      data.append('file', file)
      const res = await axios.post(`${API_URL}/business-data/preview`, data, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setPreview(res.data)
      return res.data
    } catch (e) {
      alert('业务明细预解析失败: ' + (e.response?.data?.detail || e.message))
      return null
    } finally {
      setPreviewLoading(false)
    }
  }

  const saveMappingTemplate = async () => {
    setMappingSaving(true)
    try {
      await axios.put(`${API_URL}/settings/field-mappings`, {
        template_name: templateName,
        mappings: fieldMappings
      })
      alert('字段映射模板已保存')
    } catch (e) {
      alert('保存映射失败: ' + (e.response?.data?.detail || e.message))
    } finally {
      setMappingSaving(false)
    }
  }

  const nextStep = async () => {
    if (step === 1) {
      if (!formData.customer || !formData.period || !formData.target_amount) {
        alert('请填写基础信息')
        return
      }
      setStep(2)
      return
    }
    if (step === 2) {
      if (!file && !formData.no_data_reason.trim()) {
        alert('请上传业务明细，或填写无明细原因')
        return
      }
      if (file) {
        const previewData = await parsePreview()
        if (!previewData) {
          return
        }
      } else {
        setPreview(null)
      }
      setStep(3)
    }
  }

  const handleSubmit = async () => {
    setLoading(true)
    try {
      const data = new FormData()
      data.append('target_amount', parseFloat(formData.target_amount))
      data.append('customer', formData.customer)
      data.append('period', formData.period)
      data.append('template_name', templateName)
      data.append('mappings_json', JSON.stringify(fieldMappings))
      data.append('no_data_reason', formData.no_data_reason || '')
      if (file) {
        data.append('file', file)
      }

      await axios.post(`${API_URL}/statements`, data, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      })
      onSuccess()
    } catch (err) {
      alert('生成失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6 flex items-center gap-4">
        <button onClick={onCancel} className="text-gray-500 hover:text-gray-700">&larr; 返回</button>
        <h2 className="text-2xl font-bold">新建对账单</h2>
      </div>

      <div className="mb-4 text-sm text-gray-600">步骤 {step}/3：{step === 1 ? '基础信息' : step === 2 ? '结算依据' : '预览并生成'}</div>

      <div className="bg-white shadow rounded-lg p-6 space-y-6">
        {step === 1 && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700">客户名称</label>
              <input
                required
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 border p-2"
                value={formData.customer}
                onChange={e => setFormData({ ...formData, customer: e.target.value })}
                placeholder="请输入客户名称"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">账期 (如: 2025-04 或 2025-Q2)</label>
              <input
                required
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 border p-2"
                value={formData.period}
                onChange={e => setFormData({ ...formData, period: e.target.value })}
                placeholder="请输入账期"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">目标金额 (¥)</label>
              <input
                type="number"
                step="0.01"
                required
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 border p-2"
                value={formData.target_amount}
                onChange={e => setFormData({ ...formData, target_amount: e.target.value })}
                placeholder="请输入金额"
              />
            </div>
            <div className="rounded-md border border-blue-200 bg-blue-50 p-4">
              <div className="text-sm font-medium text-blue-900">业务明细上传入口</div>
              <input
                type="file"
                accept=".xlsx,.xls"
                className="mt-2 block w-full text-sm text-gray-500
                  file:mr-4 file:py-2 file:px-4
                  file:rounded-md file:border-0
                  file:text-sm file:font-semibold
                  file:bg-blue-600 file:text-white
                  hover:file:bg-blue-700"
                onChange={e => {
                  setFile(e.target.files[0] || null)
                  setPreview(null)
                }}
              />
              <p className="mt-1 text-xs text-blue-800">
                已上传：{file ? file.name : '未上传（可在下一步做映射确认）'}
              </p>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700">结算依据文件</label>
              <input
                type="file"
                accept=".xlsx,.xls"
                className="mt-1 block w-full text-sm text-gray-500
                  file:mr-4 file:py-2 file:px-4
                  file:rounded-md file:border-0
                  file:text-sm file:font-semibold
                  file:bg-blue-50 file:text-blue-700
                  hover:file:bg-blue-100"
                onChange={e => {
                  setFile(e.target.files[0] || null)
                  setPreview(null)
                }}
              />
              <p className="mt-1 text-xs text-gray-500">如第1步已上传可不再选择。当前：{file ? file.name : '未上传'}</p>
            </div>
            {file && (
              <div className="rounded-md border border-gray-200 p-4">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-gray-700">字段映射确认</label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={parsePreview}
                      disabled={previewLoading}
                      className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
                    >
                      {previewLoading ? '解析中...' : '预解析'}
                    </button>
                    <button
                      type="button"
                      onClick={saveMappingTemplate}
                      disabled={mappingSaving}
                      className="px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 rounded-md hover:bg-blue-100 disabled:opacity-50"
                    >
                      {mappingSaving ? '保存中...' : '保存映射模板'}
                    </button>
                  </div>
                </div>

                {preview && (
                  <div className="mt-3 space-y-3">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm text-gray-700">
                      <div>总行数：{preview.rows_total}</div>
                      <div>使用行数：{preview.rows_used}</div>
                      <div>匹配列：{preview.matched_columns.length}</div>
                      <div>未匹配列：{preview.unmatched_columns.length}</div>
                    </div>
                    {preview.unmatched_columns.length > 0 ? (
                      <div className="space-y-2">
                        {preview.unmatched_columns.map((col) => (
                          <div key={col} className="grid grid-cols-1 md:grid-cols-2 gap-2 items-center">
                            <div className="text-sm text-gray-700">{col}</div>
                            <select
                              value={fieldMappings[col] || ''}
                              className="border rounded-md p-2 text-sm"
                              onChange={e => setFieldMappings({ ...fieldMappings, [col]: e.target.value })}
                            >
                              <option value="">不映射</option>
                              {billingItemNames.map(name => (
                                <option key={`${col}-${name}`} value={name}>{name}</option>
                              ))}
                            </select>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-green-700">当前未发现未匹配字段。</p>
                    )}
                  </div>
                )}
                {!preview && <p className="mt-2 text-xs text-gray-500">请先点击“预解析”加载字段匹配结果。</p>}
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700">无明细原因（若不上传必填）</label>
              <textarea
                rows={3}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 border p-2"
                value={formData.no_data_reason}
                onChange={e => setFormData({ ...formData, no_data_reason: e.target.value })}
                placeholder="例如：客户暂未提供本账期业务明细，先按人工补录流程处理。"
              />
            </div>
          </>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <div className="rounded-md border border-gray-200 p-4 bg-gray-50">
              <div className="text-sm text-gray-700">客户：{formData.customer}</div>
              <div className="text-sm text-gray-700">账期：{formData.period}</div>
              <div className="text-sm text-gray-700">目标金额：¥{Number(formData.target_amount || 0).toLocaleString()}</div>
              <div className="text-sm text-gray-700">依据类型：{file ? `业务文件（${file.name}）` : '人工说明'}</div>
            </div>

            {file && preview && (
              <div className="rounded-md border border-blue-200 p-4 bg-blue-50">
                <h4 className="font-medium text-blue-900 mb-2">业务明细预解析结果</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div>总行数：{preview.rows_total}</div>
                  <div>使用行数：{preview.rows_used}</div>
                  <div>匹配列：{preview.matched_columns.length}</div>
                  <div>未匹配列：{preview.unmatched_columns.length}</div>
                </div>
                {preview.unmatched_columns.length > 0 && (
                  <p className="mt-2 text-xs text-amber-700">存在未匹配字段：{preview.unmatched_columns.join('、')}</p>
                )}
                {Object.keys(fieldMappings).length > 0 && (
                  <p className="mt-2 text-xs text-blue-800">
                    已配置映射：{Object.entries(fieldMappings).filter(([, v]) => !!v).map(([k, v]) => `${k}->${v}`).join('；') || '无'}
                  </p>
                )}
              </div>
            )}

            {!file && (
              <div className="rounded-md border border-amber-200 p-4 bg-amber-50 text-sm text-amber-800">
                无业务明细，将按人工说明生成并记录审计原因：{formData.no_data_reason || '（未填写）'}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-3 pt-4">
          <button
            type="button"
            onClick={() => (step === 1 ? onCancel() : setStep(step - 1))}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            {step === 1 ? '取消' : '上一步'}
          </button>
          {step < 3 && (
            <button
              type="button"
              onClick={nextStep}
              disabled={previewLoading}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {previewLoading ? '解析中...' : '下一步'}
            </button>
          )}
          {step === 3 && (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={loading}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? '生成中...' : '确认生成草稿'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
