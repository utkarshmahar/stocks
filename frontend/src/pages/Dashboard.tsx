import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { apiFetch } from '../hooks/useApi'
import { useWebSocket } from '../hooks/useWebSocket'

interface Quote {
  symbol: string
  price: number
  bid: number
  ask: number
  change: number
  percent_change: number
  volume: number
  high: number
  low: number
  open: number
}

interface OptionContract {
  strike: number
  expiration: string
  bid: number
  ask: number
  last: number
  mark: number
  volume: number
  open_interest: number
  iv: number
  delta: number
  gamma: number
  theta: number
  vega: number
  dte: number
  itm: boolean
}

export default function Dashboard() {
  const [selectedSymbol, setSelectedSymbol] = useState('PANW')
  const [priceHistory, setPriceHistory] = useState<{ time: string; price: number }[]>([])

  const wsUrl = `ws://${window.location.hostname}:8000/ws/options`
  const { lastMessage, connected } = useWebSocket(wsUrl)

  const { data: watchlist } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => apiFetch<any[]>('/watchlist'),
  })

  const { data: quote } = useQuery({
    queryKey: ['quote', selectedSymbol],
    queryFn: () => apiFetch<Quote>(`/quote/${selectedSymbol}`),
    refetchInterval: 15000,
  })

  const { data: options } = useQuery({
    queryKey: ['options', selectedSymbol],
    queryFn: () => apiFetch<{ calls: OptionContract[]; puts: OptionContract[] }>(`/options/${selectedSymbol}`),
    refetchInterval: 30000,
  })

  // Update price history from WebSocket
  useEffect(() => {
    if (lastMessage?.symbol === selectedSymbol && lastMessage?.quote?.price) {
      setPriceHistory(prev => {
        const next = [...prev, { time: new Date().toLocaleTimeString(), price: lastMessage.quote.price }]
        return next.slice(-60)
      })
    }
  }, [lastMessage, selectedSymbol])

  // Group options by expiration
  const expirations = useMemo(() => {
    if (!options) return []
    const exps = new Set<string>()
    options.calls.forEach(c => exps.add(c.expiration))
    options.puts.forEach(p => exps.add(p.expiration))
    return Array.from(exps).sort()
  }, [options])

  const [selectedExp, setSelectedExp] = useState('')
  useEffect(() => {
    if (expirations.length > 0 && !selectedExp) setSelectedExp(expirations[0])
  }, [expirations, selectedExp])

  const filteredCalls = options?.calls.filter(c => c.expiration === selectedExp) || []
  const filteredPuts = options?.puts.filter(p => p.expiration === selectedExp) || []

  const activeSymbols = watchlist?.filter((w: any) => w.active).map((w: any) => w.symbol) || ['PANW', 'QCOM', 'CSCO']

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Live Options Monitor</h1>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
          <span className="text-xs text-gray-500">{connected ? 'Live' : 'Disconnected'}</span>
        </div>
      </div>

      {/* Symbol Selector */}
      <div className="flex gap-2">
        {activeSymbols.map((sym: string) => (
          <button
            key={sym}
            onClick={() => { setSelectedSymbol(sym); setPriceHistory([]) }}
            className={`px-4 py-2 rounded font-medium text-sm transition-colors ${
              selectedSymbol === sym
                ? 'bg-emerald-600 text-white'
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            {sym}
          </button>
        ))}
      </div>

      {/* Quote Card */}
      {quote && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <div className="flex items-baseline gap-4">
            <span className="text-3xl font-bold">${quote.price.toFixed(2)}</span>
            <span className={`text-lg font-medium ${quote.change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {quote.change >= 0 ? '+' : ''}{quote.change.toFixed(2)} ({quote.percent_change.toFixed(2)}%)
            </span>
          </div>
          <div className="grid grid-cols-4 gap-4 mt-4 text-sm text-gray-400">
            <div>Bid: <span className="text-gray-200">${quote.bid.toFixed(2)}</span></div>
            <div>Ask: <span className="text-gray-200">${quote.ask.toFixed(2)}</span></div>
            <div>High: <span className="text-gray-200">${quote.high.toFixed(2)}</span></div>
            <div>Low: <span className="text-gray-200">${quote.low.toFixed(2)}</span></div>
            <div>Open: <span className="text-gray-200">${quote.open.toFixed(2)}</span></div>
            <div>Volume: <span className="text-gray-200">{quote.volume.toLocaleString()}</span></div>
          </div>
        </div>
      )}

      {/* Price Chart */}
      {priceHistory.length > 1 && (
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Intraday Price</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={priceHistory}>
              <XAxis dataKey="time" tick={{ fontSize: 10 }} stroke="#666" />
              <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10 }} stroke="#666" />
              <Tooltip
                contentStyle={{ background: '#1f2937', border: '1px solid #374151' }}
                labelStyle={{ color: '#9ca3af' }}
              />
              <Line type="monotone" dataKey="price" stroke="#10b981" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Expiration Selector */}
      {expirations.length > 0 && (
        <div className="flex gap-2 overflow-x-auto">
          {expirations.map(exp => (
            <button
              key={exp}
              onClick={() => setSelectedExp(exp)}
              className={`px-3 py-1 rounded text-xs font-medium whitespace-nowrap ${
                selectedExp === exp ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {exp}
            </button>
          ))}
        </div>
      )}

      {/* Options Chain Table */}
      <div className="grid grid-cols-2 gap-4">
        {/* Calls */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          <div className="p-3 bg-emerald-900/30 border-b border-gray-800">
            <h3 className="text-sm font-bold text-emerald-400">CALLS</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="p-2 text-left">Strike</th>
                  <th className="p-2 text-right">Bid</th>
                  <th className="p-2 text-right">Ask</th>
                  <th className="p-2 text-right">Vol</th>
                  <th className="p-2 text-right">OI</th>
                  <th className="p-2 text-right">IV</th>
                  <th className="p-2 text-right">Delta</th>
                </tr>
              </thead>
              <tbody>
                {filteredCalls.sort((a, b) => a.strike - b.strike).map((c, i) => (
                  <tr key={i} className={`border-b border-gray-800/50 ${c.itm ? 'bg-emerald-900/10' : ''}`}>
                    <td className="p-2 font-medium">{c.strike.toFixed(1)}</td>
                    <td className="p-2 text-right">{c.bid.toFixed(2)}</td>
                    <td className="p-2 text-right">{c.ask.toFixed(2)}</td>
                    <td className="p-2 text-right">{c.volume}</td>
                    <td className="p-2 text-right">{c.open_interest}</td>
                    <td className="p-2 text-right">{(c.iv).toFixed(1)}%</td>
                    <td className="p-2 text-right">{c.delta.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Puts */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          <div className="p-3 bg-red-900/30 border-b border-gray-800">
            <h3 className="text-sm font-bold text-red-400">PUTS</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="p-2 text-left">Strike</th>
                  <th className="p-2 text-right">Bid</th>
                  <th className="p-2 text-right">Ask</th>
                  <th className="p-2 text-right">Vol</th>
                  <th className="p-2 text-right">OI</th>
                  <th className="p-2 text-right">IV</th>
                  <th className="p-2 text-right">Delta</th>
                </tr>
              </thead>
              <tbody>
                {filteredPuts.sort((a, b) => a.strike - b.strike).map((p, i) => (
                  <tr key={i} className={`border-b border-gray-800/50 ${p.itm ? 'bg-red-900/10' : ''}`}>
                    <td className="p-2 font-medium">{p.strike.toFixed(1)}</td>
                    <td className="p-2 text-right">{p.bid.toFixed(2)}</td>
                    <td className="p-2 text-right">{p.ask.toFixed(2)}</td>
                    <td className="p-2 text-right">{p.volume}</td>
                    <td className="p-2 text-right">{p.open_interest}</td>
                    <td className="p-2 text-right">{(p.iv).toFixed(1)}%</td>
                    <td className="p-2 text-right">{p.delta.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
