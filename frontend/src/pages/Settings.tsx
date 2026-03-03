import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../hooks/useApi'

export default function Settings() {
  const queryClient = useQueryClient()
  const [newSymbol, setNewSymbol] = useState('')

  const { data: watchlist } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => apiFetch<any[]>('/watchlist'),
  })

  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: () => apiFetch<Record<string, { value: any; description: string }>>('/config'),
  })

  const { data: health } = useQuery({
    queryKey: ['services-health'],
    queryFn: () => apiFetch<Record<string, string>>('/services/health'),
    refetchInterval: 30000,
  })

  const addSymbol = useMutation({
    mutationFn: (symbol: string) => apiFetch('/watchlist', {
      method: 'POST',
      body: JSON.stringify({ symbol }),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] })
      setNewSymbol('')
    },
  })

  const removeSymbol = useMutation({
    mutationFn: (symbol: string) => apiFetch(`/watchlist/${symbol}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watchlist'] }),
  })

  const updateConfig = useMutation({
    mutationFn: ({ key, value }: { key: string; value: any }) =>
      apiFetch(`/config/${key}`, {
        method: 'PUT',
        body: JSON.stringify({ value }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['config'] }),
  })

  const healthColors: Record<string, string> = {
    healthy: 'text-emerald-400',
    unhealthy: 'text-red-400',
    unavailable: 'text-gray-500',
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Watchlist */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <h2 className="text-lg font-medium mb-4">Watchlist</h2>
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={newSymbol}
            onChange={e => setNewSymbol(e.target.value.toUpperCase())}
            placeholder="Add symbol..."
            className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-emerald-500"
            onKeyDown={e => e.key === 'Enter' && newSymbol && addSymbol.mutate(newSymbol)}
          />
          <button
            onClick={() => newSymbol && addSymbol.mutate(newSymbol)}
            className="px-4 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-500"
          >
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {watchlist?.map((w: any) => (
            <div
              key={w.symbol}
              className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm ${
                w.active ? 'bg-gray-800 text-gray-200' : 'bg-gray-800/50 text-gray-500 line-through'
              }`}
            >
              {w.symbol}
              <button
                onClick={() => removeSymbol.mutate(w.symbol)}
                className="text-gray-500 hover:text-red-400 text-xs"
              >
                x
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Agent Config */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <h2 className="text-lg font-medium mb-4">Agent Parameters</h2>
        <div className="space-y-4">
          {config && Object.entries(config).map(([key, { value, description }]) => (
            <div key={key} className="flex items-center justify-between">
              <div>
                <span className="text-sm font-medium">{key.replace(/_/g, ' ')}</span>
                <p className="text-xs text-gray-500">{description}</p>
              </div>
              <div className="text-sm bg-gray-800 px-3 py-1 rounded">
                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Service Health */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <h2 className="text-lg font-medium mb-4">Service Health</h2>
        <div className="grid grid-cols-3 gap-3">
          {health && Object.entries(health).map(([name, status]) => (
            <div key={name} className="flex items-center gap-2 text-sm">
              <span className={`w-2 h-2 rounded-full ${
                status === 'healthy' ? 'bg-emerald-400' : status === 'unhealthy' ? 'bg-red-400' : 'bg-gray-600'
              }`} />
              <span className="text-gray-400">{name}</span>
              <span className={healthColors[status] || 'text-gray-500'}>{status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
