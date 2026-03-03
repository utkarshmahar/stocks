import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { apiFetch } from '../hooks/useApi'

export default function FundamentalAgent() {
  const [symbol, setSymbol] = useState('')
  const [activeSymbol, setActiveSymbol] = useState('')

  const { data: report } = useQuery({
    queryKey: ['fundamental', activeSymbol],
    queryFn: () => apiFetch<any>(`/fundamental/${activeSymbol}`),
    enabled: !!activeSymbol,
  })

  const analyze = useMutation({
    mutationFn: (sym: string) =>
      fetch(`/api/fundamental/${sym}/analyze` , { method: 'POST', headers: { 'Content-Type': 'application/json' } })
        .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
        .catch(() =>
          fetch(`http://${window.location.hostname}:8060/api/fundamental/${sym}/analyze`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
          }).then(r => r.json())
        ),
    onSuccess: (_, sym) => setActiveSymbol(sym),
  })

  const reportData = report?.report_data ? (typeof report.report_data === 'string' ? JSON.parse(report.report_data) : report.report_data) : null

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Fundamental Analysis</h1>

      {/* Symbol Input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={symbol}
          onChange={e => setSymbol(e.target.value.toUpperCase())}
          placeholder="Enter symbol..."
          className="px-4 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-emerald-500"
          onKeyDown={e => e.key === 'Enter' && symbol && analyze.mutate(symbol)}
        />
        <button
          onClick={() => symbol && analyze.mutate(symbol)}
          disabled={analyze.isPending || !symbol}
          className="px-4 py-2 bg-emerald-600 text-white rounded font-medium text-sm hover:bg-emerald-500 disabled:opacity-50"
        >
          {analyze.isPending ? 'Analyzing...' : 'Analyze'}
        </button>
      </div>

      {analyze.data && !report && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <h2 className="text-xl font-bold mb-4">{analyze.data.symbol} Analysis</h2>
          {analyze.data.report && (
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-medium text-gray-400">Thesis</h3>
                <p className="text-gray-200 mt-1">{analyze.data.report.thesis}</p>
              </div>
              <div>
                <h3 className="text-sm font-medium text-gray-400">Valuation Summary</h3>
                <p className="text-gray-200 mt-1">{analyze.data.report.valuation_summary}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Report Display */}
      {reportData && (
        <div className="space-y-6">
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <h2 className="text-xl font-bold mb-2">{activeSymbol}</h2>
            {report.current_price && (
              <div className="text-sm text-gray-400 mb-4">
                Current: ${report.current_price} | Intrinsic: ${report.intrinsic_value || 'N/A'} |
                Upside: {report.upside_percent ? `${report.upside_percent.toFixed(1)}%` : 'N/A'}
              </div>
            )}

            {reportData.thesis && (
              <div className="mb-4">
                <h3 className="text-sm font-medium text-gray-400 mb-1">Thesis</h3>
                <p className="text-gray-200">{reportData.thesis}</p>
              </div>
            )}

            {reportData.valuation_summary && (
              <div className="mb-4">
                <h3 className="text-sm font-medium text-gray-400 mb-1">Valuation</h3>
                <p className="text-gray-200">{reportData.valuation_summary}</p>
              </div>
            )}

            {reportData.risks?.length > 0 && (
              <div className="mb-4">
                <h3 className="text-sm font-medium text-gray-400 mb-1">Risks</h3>
                <ul className="list-disc list-inside text-sm text-gray-300">
                  {reportData.risks.map((r: string, i: number) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            )}

            {reportData.moat_assessment && (
              <div>
                <h3 className="text-sm font-medium text-gray-400 mb-1">Moat</h3>
                <p className="text-sm text-gray-300">{reportData.moat_assessment}</p>
              </div>
            )}
          </div>

          {/* Charts */}
          <div className="grid grid-cols-2 gap-4">
            {reportData.revenue_growth?.length > 0 && (
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <h3 className="text-sm font-medium text-gray-400 mb-2">Revenue Growth</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={reportData.revenue_growth}>
                    <XAxis dataKey="year" tick={{ fontSize: 10 }} stroke="#666" />
                    <YAxis tick={{ fontSize: 10 }} stroke="#666" />
                    <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151' }} />
                    <Bar dataKey="value" fill="#10b981" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {reportData.earnings_per_share?.length > 0 && (
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <h3 className="text-sm font-medium text-gray-400 mb-2">EPS Trend</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={reportData.earnings_per_share}>
                    <XAxis dataKey="year" tick={{ fontSize: 10 }} stroke="#666" />
                    <YAxis tick={{ fontSize: 10 }} stroke="#666" />
                    <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151' }} />
                    <Line type="monotone" dataKey="value" stroke="#60a5fa" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {reportData.operating_margin?.length > 0 && (
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <h3 className="text-sm font-medium text-gray-400 mb-2">Operating Margin</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={reportData.operating_margin}>
                    <XAxis dataKey="year" tick={{ fontSize: 10 }} stroke="#666" />
                    <YAxis tick={{ fontSize: 10 }} stroke="#666" tickFormatter={(v: number) => `${v}%`} />
                    <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151' }} />
                    <Line type="monotone" dataKey="value" stroke="#f59e0b" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* DCF */}
          {reportData.dcf && (
            <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
              <h3 className="text-sm font-medium text-gray-400 mb-2">DCF Valuation</h3>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Intrinsic Value</span>
                  <div className="text-lg font-bold text-emerald-400">${reportData.dcf.intrinsic_value_per_share}</div>
                </div>
                <div>
                  <span className="text-gray-500">Enterprise Value</span>
                  <div className="text-lg font-bold">${(reportData.dcf.enterprise_value / 1e9).toFixed(2)}B</div>
                </div>
                <div>
                  <span className="text-gray-500">Growth Rate</span>
                  <div className="text-lg font-bold">{(reportData.dcf.assumptions.growth_rate * 100).toFixed(0)}%</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {!reportData && !analyze.isPending && !analyze.data && (
        <div className="text-gray-500 text-center py-12">
          Enter a symbol and click Analyze to run fundamental analysis
        </div>
      )}
    </div>
  )
}
