import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

const API_URL = 'http://localhost:8000'

function cn(...inputs) {
  return twMerge(clsx(inputs))
}

export default function StatementDetail({ id, onBack }) {
  const [record, setRecord] = useState(null)
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [showSources, setShowSources] = useState(false)
  const [showRules, setShowRules] = useState(false)

  useEffect(() => {
    loadRecord()
  }, [id])

  const loadRecord = async () => {
    try {
      const [recordRes, sourceRes] = await Promise.all([
        axios.get(`${API_URL}/statements/${id}`),
        axios.get(`${API_URL}/statements/${id}/sources`)
      ])
      setRecord(recordRes.data)
      setSources(sourceRes.data || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async () => {
    try {
      const res = await axios.post(`${API_URL}/statements/${id}/export`, {}, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `Statement_${record.statement.customer}_${record.statement.period}.xlsx`)
      document.body.appendChild(link)
      link.click()
      loadRecord() // Reload to update status if changed
    } catch (e) {
      alert('导出失败')
    }
  }

  // Group items by level
  const groupedItems = useMemo(() => {
    if (!record?.statement?.items) return {}
    const groups = { L1: [], L2: [], L3: [], L4: [] }
    record.statement.items.forEach(item => {
      const level = item.level.split(' ')[0] // "L1" from "L1 System..."
      // Simple mapping or fallback
      if (level.startsWith('L1')) groups.L1.push(item)
      else if (level.startsWith('L2')) groups.L2.push(item)
      else if (level.startsWith('L3')) groups.L3.push(item)
      else if (level.startsWith('L4')) groups.L4.push(item)
      else groups.L4.push(item) // Fallback
    })
    return groups
  }, [record])

  if (loading) return (
    <div className="min-h-[400px] flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  )
  
  if (!record) return (
    <div className="p-8 text-center text-gray-500">
      <p>未找到相关记录</p>
      <button onClick={onBack} className="mt-4 text-blue-600 hover:underline">返回列表</button>
    </div>
  )

  const { statement, status } = record
  const warnings = statement.summary.warnings || []
  const targetAmount = statement.target_amount
  const generatedAmount = statement.summary.generated_amount
  const difference = targetAmount - generatedAmount
  const matchRate = targetAmount ? (generatedAmount / targetAmount) * 100 : 0
  const isPerfectMatch = Math.abs(difference) < 0.01

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* 1. Top Navigation & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button 
            onClick={onBack} 
            className="p-2 hover:bg-gray-100 rounded-full transition-colors text-gray-500"
            title="返回"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">对账单详情</h1>
            <div className="text-sm text-gray-500 flex items-center gap-2">
              <span>单号: {record.id}</span>
              <span className="w-1 h-1 bg-gray-300 rounded-full"></span>
              <span>创建于 {new Date(record.created_at).toLocaleString()}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
           <StatusBadge status={status} size="lg" />
           <button 
             onClick={handleExport} 
             className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 shadow-sm transition-all active:scale-95"
           >
             <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
             导出 Excel
           </button>
        </div>
      </div>

      {/* 2. Target vs Actual Comparison (Key Requirement: Separation) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Target Data Card */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-blue-500"></div>
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">目标设定 (Target)</h3>
              <div className="mt-1 text-2xl font-bold text-gray-900">{statement.customer}</div>
              <div className="text-sm text-gray-600">{statement.period}</div>
            </div>
            <div className="p-2 bg-blue-50 rounded-lg">
              <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
            </div>
          </div>
          <div className="mt-6">
            <div className="text-sm text-gray-500 mb-1">目标开票金额</div>
            <div className="text-4xl font-bold text-blue-600">
              ¥{targetAmount.toLocaleString()}
            </div>
          </div>
        </div>

        {/* Actual Data Card */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 relative overflow-hidden">
          <div className={cn("absolute top-0 left-0 w-1 h-full", isPerfectMatch ? "bg-green-500" : "bg-amber-500")}></div>
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">实际生成 (Actual)</h3>
              <div className="flex items-center gap-2 mt-1">
                 <span className={cn(
                   "text-sm px-2 py-0.5 rounded font-medium",
                   isPerfectMatch ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"
                 )}>
                   {isPerfectMatch ? "完美匹配" : "存在差异"}
                 </span>
                 <span className="text-sm text-gray-500">完成度 {matchRate.toFixed(2)}%</span>
              </div>
            </div>
            <div className={cn("p-2 rounded-lg", isPerfectMatch ? "bg-green-50" : "bg-amber-50")}>
              <svg className={cn("w-6 h-6", isPerfectMatch ? "text-green-600" : "text-amber-600")} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
          </div>
          <div className="mt-6 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div>
              <div className="text-sm text-gray-500 mb-1">生成总金额</div>
              <div className="text-4xl font-bold text-gray-900">
                ¥{generatedAmount.toLocaleString()}
              </div>
            </div>
            {!isPerfectMatch && (
              <div className="text-right">
                <div className="text-sm text-gray-500 mb-1">差异金额</div>
                <div className="text-xl font-semibold text-amber-600">
                  {difference > 0 ? '-' : '+'}{Math.abs(difference).toLocaleString()}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 3. Warnings Section */}
      {warnings.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3 animate-pulse-once">
          <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" /></svg>
          <div>
            <h4 className="text-sm font-semibold text-red-800">存在以下校验警告</h4>
            <ul className="mt-1 text-sm text-red-700 list-disc list-inside">
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* 4. Detailed Breakdown (Grouped by Level) */}
      <div className="space-y-6">
        <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
          <span>账单明细</span>
          <span className="text-sm font-normal text-gray-500">({statement.items.length} 项)</span>
        </h3>
        
        {['L1', 'L2', 'L3', 'L4'].map(levelKey => {
           const items = groupedItems[levelKey]
           if (!items || items.length === 0) return null
           
           const levelTotal = items.reduce((sum, item) => sum + item.amount, 0)
           const levelRatio = targetAmount ? (levelTotal / targetAmount) * 100 : 0
           const levelName = items[0]?.level || levelKey // Use first item's full level name e.g. "L1 系统收费层"

           return (
             <div key={levelKey} className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
               <div className="bg-gray-50 px-6 py-3 border-b border-gray-200 flex justify-between items-center">
                 <div className="flex items-center gap-3">
                   <span className="font-semibold text-gray-800">{levelName}</span>
                   <span className="text-xs px-2 py-0.5 bg-gray-200 text-gray-600 rounded-full">
                     {items.length} 项
                   </span>
                 </div>
                 <div className="text-sm text-gray-600">
                   小计: <span className="font-medium text-gray-900">¥{levelTotal.toLocaleString()}</span>
                   <span className="mx-2 text-gray-300">|</span>
                   占比: {levelRatio.toFixed(2)}%
                 </div>
               </div>
               
               <div className="overflow-x-auto">
                 <table className="min-w-full divide-y divide-gray-200">
                   <thead className="bg-white">
                     <tr>
                       <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-32">计费分类</th>
                       <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">收费项</th>
                       <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">单位</th>
                       <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-32">单价</th>
                       <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-32">数量</th>
                       <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-32">金额</th>
                       <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-40">数据来源</th>
                       <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">计费说明</th>
                     </tr>
                   </thead>
                   <tbody className="divide-y divide-gray-100">
                     {items.map((item, idx) => (
                       <tr key={idx} className="hover:bg-blue-50/30 transition-colors">
                         <td className="px-6 py-4 text-sm text-gray-600">{item.category || '-'}</td>
                         <td className="px-6 py-4 text-sm font-medium text-gray-900">{item.name}</td>
                         <td className="px-6 py-4 text-sm text-gray-500">{item.unit}</td>
                         <td className="px-6 py-4 text-sm text-gray-900 text-right">{Number(item.price).toLocaleString()}</td>
                         <td className="px-6 py-4 text-sm text-gray-900 text-right">{item.quantity}</td>
                         <td className="px-6 py-4 text-sm font-medium text-blue-700 text-right">{Number(item.amount).toLocaleString()}</td>
                         <td className="px-6 py-4 text-sm">
                           <SourceTag source={item.source} />
                         </td>
                         <td className="px-6 py-4 text-xs text-gray-500 max-w-xs truncate" title={item.billing_note}>
                           {item.billing_note || '-'}
                         </td>
                       </tr>
                     ))}
                   </tbody>
                 </table>
               </div>
             </div>
           )
        })}
      </div>

      {/* 5. Collapsible Additional Info (Sources & Rules) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4">
        {/* Sources Panel */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
          <button 
            onClick={() => setShowSources(!showSources)}
            className="w-full px-6 py-4 flex justify-between items-center bg-gray-50 hover:bg-gray-100 transition-colors rounded-t-lg"
          >
            <h3 className="font-semibold text-gray-700">结算依据 & 审计追踪</h3>
            <svg className={cn("w-5 h-5 text-gray-400 transition-transform", showSources ? "rotate-180" : "")} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          </button>
          
          {showSources && (
            <div className="p-6 border-t border-gray-200">
               {sources.length === 0 ? (
                 <p className="text-sm text-gray-500">无依据记录</p>
               ) : (
                 <div className="space-y-4">
                   {sources.map(s => (
                     <div key={s.id} className="text-sm border-l-2 border-blue-200 pl-3 py-1">
                       <div className="font-medium text-gray-900">
                         {s.source_type === 'BUSINESS_FILE' ? '业务文件上传' : '人工说明录入'}
                       </div>
                       <div className="text-gray-500 mt-1">
                         文件名: {s.source_name || '无'}
                       </div>
                       {s.no_data_reason && (
                         <div className="text-amber-600 mt-1">原因: {s.no_data_reason}</div>
                       )}
                       <div className="text-xs text-gray-400 mt-2 flex gap-4">
                         <span>行数: {s.rows_used}/{s.rows_total}</span>
                         <span>ID: {s.id}</span>
                       </div>
                     </div>
                   ))}
                 </div>
               )}
            </div>
          )}
        </div>

        {/* Rules Panel */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
          <button 
            onClick={() => setShowRules(!showRules)}
            className="w-full px-6 py-4 flex justify-between items-center bg-gray-50 hover:bg-gray-100 transition-colors rounded-t-lg"
          >
            <h3 className="font-semibold text-gray-700">规则快照</h3>
             <svg className={cn("w-5 h-5 text-gray-400 transition-transform", showRules ? "rotate-180" : "")} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          </button>
          
          {showRules && (
            <div className="p-6 border-t border-gray-200">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-gray-500">模板名称</div>
                  <div className="font-medium">{record.rule_template_name || 'standard'}</div>
                </div>
                <div>
                  <div className="text-gray-500">版本号</div>
                  <div className="font-medium">v{record.rule_template_version || '-'}</div>
                </div>
                <div>
                  <div className="text-gray-500">使用策略</div>
                  <div className="font-medium">{record.rule_strategy_name || '-'}</div>
                </div>
                <div>
                  <div className="text-gray-500">生成时间</div>
                  <div className="font-medium">{new Date(record.created_at).toLocaleDateString()}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status, size = 'md' }) {
  const styles = {
    DRAFT: "bg-gray-100 text-gray-800 border-gray-200",
    EXPORTED: "bg-green-50 text-green-700 border-green-200"
  }
  
  const labels = {
    DRAFT: "草稿 (Draft)",
    EXPORTED: "已导出 (Exported)"
  }

  return (
    <span className={cn(
      "inline-flex items-center justify-center rounded-full font-medium border",
      styles[status] || styles.DRAFT,
      size === 'lg' ? "px-4 py-1.5 text-sm" : "px-2.5 py-0.5 text-xs"
    )}>
      {size === 'lg' && <span className={cn("w-2 h-2 rounded-full mr-2", status === 'EXPORTED' ? 'bg-green-500' : 'bg-gray-400')}></span>}
      {labels[status] || status}
    </span>
  )
}

function SourceTag({ source }) {
  // Logic to determine color based on source text
  // Keywords based on Excel analysis: "模拟", "实际业务", "尾数调平", "基础"
  let colorClass = "bg-gray-100 text-gray-700"
  
  if (source?.includes('实际') || source?.includes('业务')) {
    colorClass = "bg-blue-50 text-blue-700 border border-blue-100"
  } else if (source?.includes('模拟')) {
    colorClass = "bg-purple-50 text-purple-700 border border-purple-100"
  } else if (source?.includes('尾差') || source?.includes('调平')) {
    colorClass = "bg-amber-50 text-amber-700 border border-amber-100"
  }

  return (
    <span className={cn("px-2 py-1 rounded text-xs font-medium whitespace-nowrap", colorClass)}>
      {source}
    </span>
  )
}
