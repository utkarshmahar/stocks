import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { apiFetch } from '../hooks/useApi'

interface Position {
  symbol: string
  quantity: number
  avg_price: number
  current_price: number | null
  market_value: number | null
  cost_basis: number | null
  pnl: number | null
  pnl_percent: number | null
  asset_type: string
  total_premium_collected?: number
  adjusted_cost_basis?: number
  effective_cost_per_share?: number
  adjusted_pnl?: number
}

export default function Portfolio() {
  const { data: positions, isLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: () => apiFetch<Position[]>('/portfolio/positions'),
  })

  const { data: premium } = useQuery({
    queryKey: ['premium'],
    queryFn: () => apiFetch<any[]>('/portfolio/premium'),
  })

  const totalValue = positions?.reduce((sum, p) => sum + (p.market_value || 0), 0) || 0
  const totalCost = positions?.reduce((sum, p) => sum + (p.cost_basis || 0), 0) || 0
  const totalPnl = totalValue - totalCost
  const totalPremium = premium?.reduce((sum, p) => sum + (p.premium_collected || 0) * (p.contracts || 1) * 100, 0) || 0

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Portfolio</h1>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <span className="text-xs text-gray-500">Total Value</span>
          <div className="text-xl font-bold">${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <span className="text-xs text-gray-500">Total P&L</span>
          <div className={`text-xl font-bold ${totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {totalPnl >= 0 ? '+' : ''}${totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <span className="text-xs text-gray-500">Premium Collected</span>
          <div className="text-xl font-bold text-emerald-400">${totalPremium.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <span className="text-xs text-gray-500">Positions</span>
          <div className="text-xl font-bold">{positions?.length || 0}</div>
        </div>
      </div>

      {/* Positions Table */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800 text-xs">
              <th className="p-3 text-left">Symbol</th>
              <th className="p-3 text-right">Qty</th>
              <th className="p-3 text-right">Avg Price</th>
              <th className="p-3 text-right">Current</th>
              <th className="p-3 text-right">Market Value</th>
              <th className="p-3 text-right">Cost Basis</th>
              <th className="p-3 text-right">P&L</th>
              <th className="p-3 text-right">P&L %</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={8} className="p-4 text-center text-gray-500">Loading...</td></tr>
            )}
            {positions?.map(p => (
              <tr key={p.symbol} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                <td className="p-3 font-medium">{p.symbol}</td>
                <td className="p-3 text-right">{p.quantity}</td>
                <td className="p-3 text-right">${p.avg_price?.toFixed(2)}</td>
                <td className="p-3 text-right">${p.current_price?.toFixed(2) || '-'}</td>
                <td className="p-3 text-right">${p.market_value?.toLocaleString(undefined, { minimumFractionDigits: 2 }) || '-'}</td>
                <td className="p-3 text-right">${p.cost_basis?.toLocaleString(undefined, { minimumFractionDigits: 2 }) || '-'}</td>
                <td className={`p-3 text-right font-medium ${(p.pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {p.pnl !== null ? `${p.pnl >= 0 ? '+' : ''}$${p.pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '-'}
                </td>
                <td className={`p-3 text-right ${(p.pnl_percent || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {p.pnl_percent !== null ? `${p.pnl_percent >= 0 ? '+' : ''}${p.pnl_percent.toFixed(2)}%` : '-'}
                </td>
              </tr>
            ))}
            {positions?.length === 0 && (
              <tr><td colSpan={8} className="p-4 text-center text-gray-500">No positions. Sync from Schwab in Settings.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Premium Collections */}
      {premium && premium.length > 0 && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          <div className="p-3 border-b border-gray-800">
            <h3 className="text-sm font-medium text-gray-400">Premium Collections</h3>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="p-2 text-left">Underlying</th>
                <th className="p-2 text-left">Strategy</th>
                <th className="p-2 text-right">Premium</th>
                <th className="p-2 text-right">Contracts</th>
                <th className="p-2 text-left">Status</th>
                <th className="p-2 text-left">Date</th>
              </tr>
            </thead>
            <tbody>
              {premium.map((pc: any) => (
                <tr key={pc.id} className="border-b border-gray-800/50">
                  <td className="p-2 font-medium">{pc.underlying_symbol}</td>
                  <td className="p-2">{pc.strategy || '-'}</td>
                  <td className="p-2 text-right text-emerald-400">${pc.premium_collected}</td>
                  <td className="p-2 text-right">{pc.contracts}</td>
                  <td className="p-2">{pc.status}</td>
                  <td className="p-2 text-gray-500">{new Date(pc.open_date).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
