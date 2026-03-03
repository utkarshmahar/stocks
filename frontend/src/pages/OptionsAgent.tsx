import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../hooks/useApi'

interface Recommendation {
  id: number
  symbol: string
  strategy: string
  legs: { action: string; strike: number; type: string; expiry: string }[]
  max_profit: number
  max_loss: number
  probability_estimate: number
  capital_required: number
  reasoning_summary: string
  risk_flags: string[]
  risk_approved: boolean | null
  risk_notes: string | null
  status: string
  generated_at: string
}

export default function OptionsAgent() {
  const queryClient = useQueryClient()
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [filterStatus, setFilterStatus] = useState<string>('')

  const { data: recommendations, isLoading } = useQuery({
    queryKey: ['recommendations', filterStatus],
    queryFn: () => apiFetch<Recommendation[]>(
      `/recommendations${filterStatus ? `?status=${filterStatus}` : ''}`
    ),
  })

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      apiFetch(`/recommendations/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['recommendations'] }),
  })

  const triggerAnalysis = useMutation({
    mutationFn: () => apiFetch('/recommendations', { method: 'POST' }).catch(() =>
      fetch('http://' + window.location.hostname + ':8030/api/agent/analyze', { method: 'POST' }).then(r => r.json())
    ),
  })

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-900/50 text-yellow-300',
    taken: 'bg-emerald-900/50 text-emerald-300',
    ignored: 'bg-gray-700 text-gray-400',
    paper_traded: 'bg-blue-900/50 text-blue-300',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Options AI Recommendations</h1>
        <button
          onClick={() => triggerAnalysis.mutate()}
          disabled={triggerAnalysis.isPending}
          className="px-4 py-2 bg-emerald-600 text-white rounded font-medium text-sm hover:bg-emerald-500 disabled:opacity-50"
        >
          {triggerAnalysis.isPending ? 'Analyzing...' : 'Run Analysis'}
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {['', 'pending', 'taken', 'ignored', 'paper_traded'].map(s => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`px-3 py-1 rounded text-xs font-medium ${
              filterStatus === s ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {isLoading && <div className="text-gray-500">Loading recommendations...</div>}

      {/* Recommendations List */}
      <div className="space-y-3">
        {recommendations?.map(rec => (
          <div key={rec.id} className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
            <div
              className="p-4 cursor-pointer hover:bg-gray-800/50"
              onClick={() => setExpandedId(expandedId === rec.id ? null : rec.id)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-lg font-bold">{rec.symbol}</span>
                  <span className="text-sm text-gray-400">{rec.strategy}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${statusColors[rec.status] || ''}`}>
                    {rec.status}
                  </span>
                  {rec.risk_approved === false && (
                    <span className="text-xs px-2 py-0.5 rounded bg-red-900/50 text-red-300">Risk Flagged</span>
                  )}
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-emerald-400">+${rec.max_profit}</span>
                  <span className="text-red-400">-${rec.max_loss}</span>
                  <span className="text-gray-400">{(rec.probability_estimate * 100).toFixed(0)}% prob</span>
                </div>
              </div>

              {/* Legs summary */}
              <div className="flex gap-2 mt-2">
                {rec.legs?.map((leg, i) => (
                  <span key={i} className="text-xs bg-gray-800 px-2 py-1 rounded">
                    {leg.action} {leg.strike} {leg.type} {leg.expiry}
                  </span>
                ))}
              </div>
            </div>

            {/* Expanded Details */}
            {expandedId === rec.id && (
              <div className="border-t border-gray-800 p-4 space-y-3">
                <div>
                  <span className="text-xs text-gray-500">Reasoning</span>
                  <p className="text-sm text-gray-300 mt-1">{rec.reasoning_summary}</p>
                </div>
                {rec.risk_flags?.length > 0 && (
                  <div>
                    <span className="text-xs text-gray-500">Risk Flags</span>
                    <div className="flex gap-1 mt-1">
                      {rec.risk_flags.map((f, i) => (
                        <span key={i} className="text-xs bg-red-900/30 text-red-300 px-2 py-0.5 rounded">{f}</span>
                      ))}
                    </div>
                  </div>
                )}
                {rec.risk_notes && (
                  <div>
                    <span className="text-xs text-gray-500">Risk Notes</span>
                    <p className="text-sm text-gray-400 mt-1">{rec.risk_notes}</p>
                  </div>
                )}
                <div className="text-xs text-gray-600">
                  Capital: ${rec.capital_required} | Generated: {new Date(rec.generated_at).toLocaleString()}
                </div>
                <div className="flex gap-2 pt-2">
                  {rec.status === 'pending' && (
                    <>
                      <button
                        onClick={() => updateStatus.mutate({ id: rec.id, status: 'taken' })}
                        className="px-3 py-1 bg-emerald-600 text-white rounded text-xs hover:bg-emerald-500"
                      >
                        Take Trade
                      </button>
                      <button
                        onClick={() => updateStatus.mutate({ id: rec.id, status: 'paper_traded' })}
                        className="px-3 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-500"
                      >
                        Paper Trade
                      </button>
                      <button
                        onClick={() => updateStatus.mutate({ id: rec.id, status: 'ignored' })}
                        className="px-3 py-1 bg-gray-700 text-gray-300 rounded text-xs hover:bg-gray-600"
                      >
                        Ignore
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {recommendations?.length === 0 && (
          <div className="text-gray-500 text-center py-8">
            No recommendations yet. Click "Run Analysis" to generate.
          </div>
        )}
      </div>
    </div>
  )
}
