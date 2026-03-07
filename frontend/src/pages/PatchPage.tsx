import { useState, useEffect } from 'react'
import { listRepos, proposePatch, type Repo, type PatchResult } from '../api/client'
import DiffViewer from '../components/DiffViewer'
import CodeBlock from '../components/CodeBlock'

export default function PatchPage() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [repoId, setRepoId] = useState('')
  const [issueDescription, setIssueDescription] = useState('')
  const [filePath, setFilePath] = useState('')
  const [result, setResult] = useState<PatchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [repoLoadError, setRepoLoadError] = useState('')

  const loadRepos = () => {
    setRepoLoadError('')
    listRepos().then(setRepos).catch((e: any) => setRepoLoadError(e?.userMessage || 'Failed to load repositories'))
  }

  useEffect(() => { loadRepos() }, [])

  const handleSubmit = async () => {
    if (!repoId || !issueDescription.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await proposePatch({
        repo_id: repoId,
        issue_description: issueDescription,
        file_path: filePath.trim() || undefined,
      })
      setResult(res)
    } catch (e) {
      setError((e as any)?.userMessage || 'An unexpected error occurred')
    } finally {
      setLoading(false)
    }
  }

  const confidenceColor = (c: number) =>
    c >= 0.7 ? 'text-green-400' : c >= 0.4 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-1">🩹 Patch Proposal</h1>
        <p className="text-slate-400 text-sm">Generate AI-powered code patches for issues and bugs</p>
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
          <label className="block text-xs font-medium text-slate-400 mb-1">Issue Description</label>
          <textarea
            rows={4}
            placeholder="Describe the bug or feature to implement…"
            value={issueDescription}
            onChange={e => setIssueDescription(e.target.value)}
            className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Target File <span className="text-slate-500">(optional)</span></label>
          <input
            type="text"
            placeholder="e.g. src/utils/auth.py"
            value={filePath}
            onChange={e => setFilePath(e.target.value)}
            className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>
        {error && <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-2 rounded text-sm">{error}</div>}
        <button
          onClick={handleSubmit}
          disabled={loading || !repoId || !issueDescription.trim()}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? 'Generating patch…' : 'Generate Patch'}
        </button>
      </div>

      {result && (
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-sm">
              <span className="text-slate-400">Target: </span>
              <span className="font-mono text-indigo-300">{result.target_file || 'unknown'}</span>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-sm">
              <span className="text-slate-400">Confidence: </span>
              <span className={`font-semibold ${confidenceColor(result.confidence)}`}>
                {(result.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>

          {result.raw_diff && (
            <div>
              <h2 className="text-sm font-semibold text-slate-300 mb-2">Diff</h2>
              <DiffViewer diff={result.raw_diff} filename={result.target_file} />
            </div>
          )}

          {result.explanation && (
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
              <h2 className="text-sm font-semibold text-slate-300 mb-2">Explanation</h2>
              <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">{result.explanation}</p>
            </div>
          )}

          {result.unit_test && (
            <div>
              <h2 className="text-sm font-semibold text-slate-300 mb-2">Suggested Unit Test</h2>
              <CodeBlock code={result.unit_test} language="python" showLineNumbers={false} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

