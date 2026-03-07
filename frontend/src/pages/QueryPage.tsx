import { useState, useEffect } from 'react'
import { listRepos, query, getErrorMessage, type Repo, type QueryResult } from '../api/client'
import CodeBlock from '../components/CodeBlock'

export default function QueryPage() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [repoId, setRepoId] = useState('')
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<QueryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [repoLoadError, setRepoLoadError] = useState('')

  const loadRepos = () => {
    setRepoLoadError('')
    listRepos().then(setRepos).catch((e) => setRepoLoadError(getErrorMessage(e)))
  }

  useEffect(() => { loadRepos() }, [])

  const handleSubmit = async () => {
    if (!repoId || !question.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await query({ repo_id: repoId, question, top_k: 8 })
      setResult(res)
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-1">🔍 AI Query</h1>
        <p className="text-slate-400 text-sm">Ask questions about your codebase using AI-powered retrieval</p>
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
          <label className="block text-xs font-medium text-slate-400 mb-1">Question</label>
          <textarea
            rows={3}
            placeholder="e.g. How does the authentication flow work?"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) handleSubmit() }}
            className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>
        {error && <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-2 rounded text-sm">{error}</div>}
        <button
          onClick={handleSubmit}
          disabled={loading || !repoId || !question.trim()}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? 'Searching…' : 'Ask AI'}
        </button>
      </div>

      {result && (
        <div className="space-y-4">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-indigo-400 text-sm font-semibold">AI Answer</span>
              {result.cached && <span className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded">cached</span>}
            </div>
            <p className="text-slate-200 text-sm whitespace-pre-wrap leading-relaxed">{result.answer}</p>
          </div>

          {result.citations.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-slate-300 mb-3">Citations ({result.citations.length})</h2>
              <div className="space-y-3">
                {result.citations.map((c, i) => (
                  <div key={i} className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-700">
                      <span className="text-xs text-slate-300 font-mono">{c.file_path}</span>
                      <span className="text-xs text-slate-500">Lines {c.start_line}–{c.end_line} · score {c.score.toFixed(2)}</span>
                    </div>
                    <CodeBlock
                      code={c.text}
                      language={c.file_path.split('.').pop() || 'text'}
                      startingLineNumber={c.start_line}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

