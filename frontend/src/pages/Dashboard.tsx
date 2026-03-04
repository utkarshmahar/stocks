import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
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

interface GreekModal {
  symbol: string
  strike: number
  expiration: string
  option_type: 'CALL' | 'PUT'
  greek: 'iv' | 'delta' | 'gamma' | 'theta'
}

interface PriceModal {
  symbol: string
  strike: number
  expiration: string
  option_type: 'CALL' | 'PUT'
  clicked: 'bid' | 'ask' | 'last'
}

interface GreekHistoryResponse {
  contract: { symbol: string; strike: number; expiration: string; option_type: string; greek: string }
  greek_history: { time: string; value: number }[]
  price_history: { time: string; value: number }[]
}

interface OptionPriceHistoryResponse {
  contract: { symbol: string; strike: number; expiration: string; option_type: string }
  bid_history: { time: string; value: number }[]
  ask_history: { time: string; value: number }[]
  last_history: { time: string; value: number }[]
  price_history: { time: string; value: number }[]
}

const GREEK_LABELS: Record<string, string> = { iv: 'IV', delta: 'Delta', gamma: 'Gamma', theta: 'Theta' }
const TIME_RANGES = ['1d', '3d', '1w', '1m'] as const

export default function Dashboard() {
  const [selectedSymbol, setSelectedSymbol] = useState('PANW')
  const [priceHistory, setPriceHistory] = useState<{ time: string; price: number }[]>([])
  const [greekModal, setGreekModal] = useState<GreekModal | null>(null)
  const [priceModal, setPriceModal] = useState<PriceModal | null>(null)
  const [timeRange, setTimeRange] = useState<string>('1d')
  const [priceTimeRange, setPriceTimeRange] = useState<string>('1d')

  // Live data from WebSocket (keyed by symbol)
  const [liveQuotes, setLiveQuotes] = useState<Record<string, Quote>>({})
  const [liveOptions, setLiveOptions] = useState<Record<string, { calls: OptionContract[]; puts: OptionContract[] }>>({})
  const lastUpdateRef = useRef<string>('')

  const wsUrl = `ws://${window.location.host}/ws/options`
  const { lastMessage, connected } = useWebSocket(wsUrl)

  const { data: watchlist } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => apiFetch<any[]>('/watchlist'),
  })

  // Initial load from InfluxDB (fallback until WebSocket data arrives)
  const { data: initialQuote } = useQuery({
    queryKey: ['quote', selectedSymbol],
    queryFn: () => apiFetch<Quote>(`/quote/${selectedSymbol}`),
    staleTime: Infinity, // only fetch once, WebSocket takes over
  })

  const { data: initialOptions } = useQuery({
    queryKey: ['options', selectedSymbol],
    queryFn: () => apiFetch<{ calls: OptionContract[]; puts: OptionContract[] }>(`/options/${selectedSymbol}`),
    staleTime: Infinity, // only fetch once, WebSocket takes over
  })

  // Use live data if available, fall back to initial HTTP fetch
  const quote = liveQuotes[selectedSymbol] || initialQuote
  const options = liveOptions[selectedSymbol] || initialOptions

  const { data: greekHistory, isLoading: greekLoading } = useQuery({
    queryKey: ['greekHistory', greekModal?.symbol, greekModal?.option_type, greekModal?.expiration, greekModal?.strike, greekModal?.greek, timeRange],
    queryFn: () => {
      if (!greekModal) return null
      const params = new URLSearchParams({
        symbol: greekModal.symbol,
        option_type: greekModal.option_type,
        expiration: greekModal.expiration,
        strike: greekModal.strike.toString(),
        greek: greekModal.greek,
        time_range: timeRange,
      })
      return apiFetch<GreekHistoryResponse>(`/history/greek?${params}`)
    },
    enabled: !!greekModal,
  })

  const { data: optionPriceHistory, isLoading: optionPriceLoading } = useQuery({
    queryKey: ['optionPriceHistory', priceModal?.symbol, priceModal?.option_type, priceModal?.expiration, priceModal?.strike, priceTimeRange],
    queryFn: () => {
      if (!priceModal) return null
      const params = new URLSearchParams({
        symbol: priceModal.symbol,
        option_type: priceModal.option_type,
        expiration: priceModal.expiration,
        strike: priceModal.strike.toString(),
        time_range: priceTimeRange,
      })
      return apiFetch<OptionPriceHistoryResponse>(`/history/option-price?${params}`)
    },
    enabled: !!priceModal,
  })

  // Process WebSocket messages — update live quote, options, and price chart
  useEffect(() => {
    if (!lastMessage?.symbol) return

    const sym = lastMessage.symbol
    const msgKey = `${sym}-${lastMessage.timestamp}`
    if (msgKey === lastUpdateRef.current) return
    lastUpdateRef.current = msgKey

    // Update live quote
    if (lastMessage.quote) {
      const q = lastMessage.quote
      setLiveQuotes(prev => ({
        ...prev,
        [sym]: {
          symbol: sym,
          price: q.price || 0,
          bid: q.bid || 0,
          ask: q.ask || 0,
          change: q.change || 0,
          percent_change: q.percent_change || 0,
          volume: q.volume || 0,
          high: q.high || 0,
          low: q.low || 0,
          open: q.open || 0,
        }
      }))
    }

    // Update live options
    if (lastMessage.calls || lastMessage.puts) {
      setLiveOptions(prev => ({
        ...prev,
        [sym]: {
          calls: lastMessage.calls || [],
          puts: lastMessage.puts || [],
        }
      }))
    }

    // Update price chart for selected symbol
    if (sym === selectedSymbol && lastMessage.quote?.price) {
      setPriceHistory(prev => {
        const next = [...prev, { time: new Date().toLocaleTimeString(), price: lastMessage.quote.price }]
        return next.slice(-60)
      })
    }
  }, [lastMessage, selectedSymbol])

  // Close modal on Escape
  useEffect(() => {
    if (!greekModal && !priceModal) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setGreekModal(null); setPriceModal(null) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [greekModal, priceModal])

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

  const openGreekModal = useCallback((contract: OptionContract, optionType: 'CALL' | 'PUT', greek: 'iv' | 'delta' | 'gamma' | 'theta') => {
    setGreekModal({
      symbol: selectedSymbol,
      strike: contract.strike,
      expiration: contract.expiration,
      option_type: optionType,
      greek,
    })
    setTimeRange('1d')
  }, [selectedSymbol])

  const openPriceModal = useCallback((contract: OptionContract, optionType: 'CALL' | 'PUT', clicked: 'bid' | 'ask' | 'last') => {
    setPriceModal({
      symbol: selectedSymbol,
      strike: contract.strike,
      expiration: contract.expiration,
      option_type: optionType,
      clicked,
    })
    setPriceTimeRange('1d')
  }, [selectedSymbol])

  const formatTime = useCallback((time: string, range: string) => {
    try {
      const d = new Date(time)
      return range === '1d' ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    } catch { return time }
  }, [])

  const formatGreekTime = useCallback((time: string) => formatTime(time, timeRange), [formatTime, timeRange])
  const formatPriceTime = useCallback((time: string) => formatTime(time, priceTimeRange), [formatTime, priceTimeRange])

  const renderGreekCell = (contract: OptionContract, optionType: 'CALL' | 'PUT', greek: 'iv' | 'delta' | 'gamma' | 'theta', value: string) => (
    <td
      className="p-2 text-right cursor-pointer hover:bg-gray-700/50 hover:text-purple-300 transition-colors rounded"
      onClick={() => openGreekModal(contract, optionType, greek)}
      title={`Click to view ${GREEK_LABELS[greek]} history`}
    >
      {value}
    </td>
  )

  const renderPriceCell = (contract: OptionContract, optionType: 'CALL' | 'PUT', field: 'bid' | 'ask' | 'last', value: string) => (
    <td
      className="p-2 text-right cursor-pointer hover:bg-gray-700/50 hover:text-blue-300 transition-colors rounded"
      onClick={() => openPriceModal(contract, optionType, field)}
      title="Click to view Bid/Ask/LTP history"
    >
      {value}
    </td>
  )

  // Merge bid/ask/last histories into a single array for combined chart
  const mergedOptionPrices = useMemo(() => {
    if (!optionPriceHistory) return []
    const timeMap = new Map<string, { time: string; bid?: number; ask?: number; last?: number }>()
    for (const p of optionPriceHistory.bid_history) {
      const entry = timeMap.get(p.time) || { time: p.time }
      entry.bid = p.value
      timeMap.set(p.time, entry)
    }
    for (const p of optionPriceHistory.ask_history) {
      const entry = timeMap.get(p.time) || { time: p.time }
      entry.ask = p.value
      timeMap.set(p.time, entry)
    }
    for (const p of optionPriceHistory.last_history) {
      const entry = timeMap.get(p.time) || { time: p.time }
      entry.last = p.value
      timeMap.set(p.time, entry)
    }
    return Array.from(timeMap.values()).sort((a, b) => a.time.localeCompare(b.time))
  }, [optionPriceHistory])

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
                  <th className="p-2 text-right">LTP</th>
                  <th className="p-2 text-right">Vol</th>
                  <th className="p-2 text-right">OI</th>
                  <th className="p-2 text-right">IV</th>
                  <th className="p-2 text-right">Delta</th>
                  <th className="p-2 text-right">Gamma</th>
                  <th className="p-2 text-right">Theta</th>
                </tr>
              </thead>
              <tbody>
                {filteredCalls.sort((a, b) => a.strike - b.strike).map((c, i) => (
                  <tr key={i} className={`border-b border-gray-800/50 ${c.itm ? 'bg-emerald-900/10' : ''}`}>
                    <td className="p-2 font-medium">{c.strike.toFixed(1)}</td>
                    {renderPriceCell(c, 'CALL', 'bid', c.bid.toFixed(2))}
                    {renderPriceCell(c, 'CALL', 'ask', c.ask.toFixed(2))}
                    {renderPriceCell(c, 'CALL', 'last', c.last.toFixed(2))}
                    <td className="p-2 text-right">{c.volume}</td>
                    <td className="p-2 text-right">{c.open_interest}</td>
                    {renderGreekCell(c, 'CALL', 'iv', `${c.iv.toFixed(1)}%`)}
                    {renderGreekCell(c, 'CALL', 'delta', c.delta.toFixed(3))}
                    {renderGreekCell(c, 'CALL', 'gamma', c.gamma.toFixed(4))}
                    {renderGreekCell(c, 'CALL', 'theta', c.theta.toFixed(3))}
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
                  <th className="p-2 text-right">LTP</th>
                  <th className="p-2 text-right">Vol</th>
                  <th className="p-2 text-right">OI</th>
                  <th className="p-2 text-right">IV</th>
                  <th className="p-2 text-right">Delta</th>
                  <th className="p-2 text-right">Gamma</th>
                  <th className="p-2 text-right">Theta</th>
                </tr>
              </thead>
              <tbody>
                {filteredPuts.sort((a, b) => a.strike - b.strike).map((p, i) => (
                  <tr key={i} className={`border-b border-gray-800/50 ${p.itm ? 'bg-red-900/10' : ''}`}>
                    <td className="p-2 font-medium">{p.strike.toFixed(1)}</td>
                    {renderPriceCell(p, 'PUT', 'bid', p.bid.toFixed(2))}
                    {renderPriceCell(p, 'PUT', 'ask', p.ask.toFixed(2))}
                    {renderPriceCell(p, 'PUT', 'last', p.last.toFixed(2))}
                    <td className="p-2 text-right">{p.volume}</td>
                    <td className="p-2 text-right">{p.open_interest}</td>
                    {renderGreekCell(p, 'PUT', 'iv', `${p.iv.toFixed(1)}%`)}
                    {renderGreekCell(p, 'PUT', 'delta', p.delta.toFixed(3))}
                    {renderGreekCell(p, 'PUT', 'gamma', p.gamma.toFixed(4))}
                    {renderGreekCell(p, 'PUT', 'theta', p.theta.toFixed(3))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Greek History Modal */}
      {greekModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setGreekModal(null) }}
        >
          <div className="bg-gray-900 rounded-xl border border-gray-700 shadow-2xl w-[95vw] max-w-7xl max-h-[90vh] overflow-auto">
            <div className="flex items-center justify-between p-5 border-b border-gray-700">
              <div>
                <h2 className="text-xl font-bold">
                  {greekModal.symbol} {greekModal.option_type} {greekModal.strike.toFixed(1)} — {greekModal.expiration}
                </h2>
                <p className="text-base text-purple-400 font-medium mt-1">{GREEK_LABELS[greekModal.greek]} History</p>
              </div>
              <button onClick={() => setGreekModal(null)} className="text-gray-400 hover:text-white text-3xl leading-none px-3">&times;</button>
            </div>
            <div className="flex gap-3 px-5 pt-5">
              {TIME_RANGES.map(r => (
                <button key={r} onClick={() => setTimeRange(r)} className={`px-4 py-1.5 rounded text-sm font-medium ${timeRange === r ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>{r}</button>
              ))}
            </div>
            <div className="p-5">
              {greekLoading ? (
                <div className="flex items-center justify-center h-96 text-gray-500 text-lg">Loading history...</div>
              ) : !greekHistory?.greek_history?.length && !greekHistory?.price_history?.length ? (
                <div className="flex items-center justify-center h-96 text-gray-500 text-lg">No historical data available for this contract and time range.</div>
              ) : (
                <div className="space-y-8">
                  <div>
                    <h3 className="text-base font-medium text-purple-400 mb-3">{GREEK_LABELS[greekModal.greek]} Over Time</h3>
                    {greekHistory?.greek_history?.length ? (
                      <ResponsiveContainer width="100%" height={350}>
                        <LineChart data={greekHistory.greek_history}>
                          <XAxis dataKey="time" tickFormatter={formatGreekTime} tick={{ fontSize: 12 }} stroke="#666" />
                          <YAxis domain={['auto', 'auto']} tick={{ fontSize: 12 }} stroke="#666" width={70} />
                          <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', fontSize: 14 }} labelStyle={{ color: '#9ca3af' }} labelFormatter={formatGreekTime} formatter={(v: number) => [v.toFixed(4), GREEK_LABELS[greekModal.greek]]} />
                          <Line type="monotone" dataKey="value" stroke="#8b5cf6" dot={false} strokeWidth={2.5} />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex items-center justify-center h-[350px] text-gray-600">No data</div>
                    )}
                  </div>
                  <div>
                    <h3 className="text-base font-medium text-emerald-400 mb-3">{greekModal.symbol} Price Over Time</h3>
                    {greekHistory?.price_history?.length ? (
                      <ResponsiveContainer width="100%" height={350}>
                        <LineChart data={greekHistory.price_history}>
                          <XAxis dataKey="time" tickFormatter={formatGreekTime} tick={{ fontSize: 12 }} stroke="#666" />
                          <YAxis domain={['auto', 'auto']} tick={{ fontSize: 12 }} stroke="#666" width={70} />
                          <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', fontSize: 14 }} labelStyle={{ color: '#9ca3af' }} labelFormatter={formatGreekTime} formatter={(v: number) => [`$${v.toFixed(2)}`, 'Price']} />
                          <Line type="monotone" dataKey="value" stroke="#10b981" dot={false} strokeWidth={2.5} />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex items-center justify-center h-[350px] text-gray-600">No data</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Option Price History Modal (Bid/Ask/LTP) */}
      {priceModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setPriceModal(null) }}
        >
          <div className="bg-gray-900 rounded-xl border border-gray-700 shadow-2xl w-[95vw] max-w-7xl max-h-[90vh] overflow-auto">
            <div className="flex items-center justify-between p-5 border-b border-gray-700">
              <div>
                <h2 className="text-xl font-bold">
                  {priceModal.symbol} {priceModal.option_type} {priceModal.strike.toFixed(1)} — {priceModal.expiration}
                </h2>
                <p className="text-base text-blue-400 font-medium mt-1">Bid / Ask / LTP History</p>
              </div>
              <button onClick={() => setPriceModal(null)} className="text-gray-400 hover:text-white text-3xl leading-none px-3">&times;</button>
            </div>
            <div className="flex gap-3 px-5 pt-5">
              {TIME_RANGES.map(r => (
                <button key={r} onClick={() => setPriceTimeRange(r)} className={`px-4 py-1.5 rounded text-sm font-medium ${priceTimeRange === r ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>{r}</button>
              ))}
            </div>
            <div className="p-5">
              {optionPriceLoading ? (
                <div className="flex items-center justify-center h-96 text-gray-500 text-lg">Loading history...</div>
              ) : !mergedOptionPrices.length && !optionPriceHistory?.price_history?.length ? (
                <div className="flex items-center justify-center h-96 text-gray-500 text-lg">No historical data available for this contract and time range.</div>
              ) : (
                <div className="space-y-8">
                  <div>
                    <h3 className="text-base font-medium text-blue-400 mb-3">Option Bid / Ask / LTP Over Time</h3>
                    {mergedOptionPrices.length ? (
                      <ResponsiveContainer width="100%" height={350}>
                        <LineChart data={mergedOptionPrices}>
                          <XAxis dataKey="time" tickFormatter={formatPriceTime} tick={{ fontSize: 12 }} stroke="#666" />
                          <YAxis domain={['auto', 'auto']} tick={{ fontSize: 12 }} stroke="#666" width={70} />
                          <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', fontSize: 14 }} labelStyle={{ color: '#9ca3af' }} labelFormatter={formatPriceTime} formatter={(v: number, name: string) => [`$${v.toFixed(2)}`, name.charAt(0).toUpperCase() + name.slice(1)]} />
                          <Legend wrapperStyle={{ fontSize: 13 }} />
                          <Line type="monotone" dataKey="bid" stroke="#f59e0b" dot={false} strokeWidth={2} name="Bid" />
                          <Line type="monotone" dataKey="ask" stroke="#ef4444" dot={false} strokeWidth={2} name="Ask" />
                          <Line type="monotone" dataKey="last" stroke="#3b82f6" dot={false} strokeWidth={2.5} name="LTP" />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex items-center justify-center h-[350px] text-gray-600">No data</div>
                    )}
                  </div>
                  <div>
                    <h3 className="text-base font-medium text-emerald-400 mb-3">{priceModal.symbol} Stock Price Over Time</h3>
                    {optionPriceHistory?.price_history?.length ? (
                      <ResponsiveContainer width="100%" height={350}>
                        <LineChart data={optionPriceHistory.price_history}>
                          <XAxis dataKey="time" tickFormatter={formatPriceTime} tick={{ fontSize: 12 }} stroke="#666" />
                          <YAxis domain={['auto', 'auto']} tick={{ fontSize: 12 }} stroke="#666" width={70} />
                          <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', fontSize: 14 }} labelStyle={{ color: '#9ca3af' }} labelFormatter={formatPriceTime} formatter={(v: number) => [`$${v.toFixed(2)}`, 'Price']} />
                          <Line type="monotone" dataKey="value" stroke="#10b981" dot={false} strokeWidth={2.5} />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex items-center justify-center h-[350px] text-gray-600">No data</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
