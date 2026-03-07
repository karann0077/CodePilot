import { useState, useEffect } from 'react'
import { listRepos, diagnose, type Repo, type DiagnoseResult } from '../api/client'

export default function DiagnosePage() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [repoId, setRepoId] = useState('')
  const [errorText, setErrorText] = useState('')
  const [stacktrace, setStacktrace] = useState('')
  const [result, setResult] = useState<DiagnoseResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [repoLoadError, setRepoLoadError] = useState('')

  const loadRepos = () => {
    setRepoLoadError('')
    listRepos().then(setRepos).catch((e: any) => setRepoLoadError(e?.userMessage || 'Failed to load repositories'))
  }

  useEffect(() => { loadRepos() }, [])

  const handleSubmit = async () => {
    if (!repoId || !errorText.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await diagnose({ repo_id: repoId, error_text: errorText, stacktrace })
      setResult(res)
    } catch (e) {
      setError((e as any)?.userMessage || 'An unexpected error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-1">🐛 Error Diagnosis</h1>
        <p className="text-slate-400 text-sm">Identify the root cause of errors using AI-powered code analysis</p>
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 mb-6 space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Repository</label>
          {repoLoadError ? (
            <div className="flex items-center gap-3">
              <span className="text-red-400 text-xs">{repoLoadError}</span>
              <button onClick={loadRepos} aria-label="Retry loading repositories" className="text-xs text-indigo-400 hover:underline">Retry</button>
            </div>
          ) : (
          <select
            value={repoId}
            onChange={e => setRepoId(e.target.value)}
            className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="">Select a repository…</option>
            {repos.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          )}
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Error Message</label>
          <textarea
            rows={2}
            placeholder="e.g. TypeError: Cannot read properties of undefined (reading 'map')"
            value={errorText}
            onChange={e => setErrorText(e.target.value)}
            className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Stack Trace <span className="text-slate-500">(optional)</span></label>
          <textarea
            rows={5}
            placeholder="Paste the full stack trace here…"
            value={stacktrace}
            onChange={e => setStacktrace(e.target.value)}
            className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white font-mono placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>
        {error && <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-2 rounded text-sm">{error}</div>}
        <button
          onClick={handleSubmit}
          disabled={loading || !repoId || !errorText.trim()}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? 'Analyzing…' : 'Diagnose'}
        </button>
      </div>

      {result && (
        <div>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">
            Suspects ({result.suspects.length})
          </h2>
          {result.suspects.length === 0 ? (
            <div className="text-slate-500 text-sm">No suspects found for this error.</div>
          ) : (
            <div className="space-y-3">
              {result.suspects.map((s, i) => (
                <div key={i} className="bg-slate-800 border border-slate-700 rounded-xl p-4">
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-sm font-mono text-indigo-300">{s.file_path}</span>
                    <span className="text-xs text-slate-500 ml-2 shrink-0">Lines {s.start_line}–{s.end_line}</span>
                  </div>
                  <div className="mb-3">
                    <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                      <span>Probability</span>
                      <span>{(s.probability * 100).toFixed(0)}%</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${s.probability >= 0.7 ? 'bg-red-500' : s.probability >= 0.4 ? 'bg-yellow-500' : 'bg-green-500'}`}
                        style={{ width: `${s.probability * 100}%` }}
                      />
                    </div>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">{s.explanation}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

