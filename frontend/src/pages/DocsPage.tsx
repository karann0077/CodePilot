import { useState, useEffect, useRef } from 'react'
import { listRepos, generateDocs, getDocResult, getErrorMessage, type Repo, type DocEntry } from '../api/client'
import CodeBlock from '../components/CodeBlock'

export default function DocsPage() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [repoId, setRepoId] = useState('')
  const [filePath, setFilePath] = useState('')
  const [docs, setDocs] = useState<DocEntry[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [statusMsg, setStatusMsg] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [repoLoadError, setRepoLoadError] = useState('')

  const loadRepos = () => {
    setRepoLoadError('')
    listRepos().then(setRepos).catch((e) => setRepoLoadError(getErrorMessage(e)))
  }

  useEffect(() => {
    loadRepos()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const handleGenerate = async () => {
    if (!repoId) return
    setLoading(true)
    setError('')
    setDocs(null)
    setStatusMsg('Starting documentation generation…')
    try {
      const job = await generateDocs({ repo_id: repoId, file_path: filePath.trim() || undefined })
      setStatusMsg('Job queued, waiting for results…')
      pollRef.current = setInterval(async () => {
        try {
          const res = await getDocResult(job.job_id)
          if (res.status === 'completed') {
            clearInterval(pollRef.current!)
            setDocs(res.docs || [])
            setLoading(false)
            setStatusMsg('')
          } else if (res.status === 'failed') {
            clearInterval(pollRef.current!)
            setError(res.error || 'Documentation generation failed.')
            setLoading(false)
            setStatusMsg('')
          } else {
            setStatusMsg(`Status: ${res.status}…`)
          }
        } catch {
          clearInterval(pollRef.current!)
          setError('Failed to fetch job status.')
          setLoading(false)
          setStatusMsg('')
        }
      }, 2000)
    } catch (e) {
      setError(getErrorMessage(e))
      setLoading(false)
      setStatusMsg('')
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-1">📚 Documentation Generator</h1>
        <p className="text-slate-400 text-sm">Generate AI-powered docstrings and documentation for your codebase</p>
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
          <label className="block text-xs font-medium text-slate-400 mb-1">File Path <span className="text-slate-500">(optional — leave blank for entire repo)</span></label>
          <input
            type="text"
            placeholder="e.g. src/utils/auth.py"
            value={filePath}
            onChange={e => setFilePath(e.target.value)}
            className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>
        {error && <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-2 rounded text-sm">{error}</div>}
        {statusMsg && <div className="text-slate-400 text-sm">{statusMsg}</div>}
        <button
          onClick={handleGenerate}
          disabled={loading || !repoId}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? 'Generating…' : 'Generate Docs'}
        </button>
      </div>

      {docs !== null && (
        <div>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">
            Generated Documentation ({docs.length} chunks)
          </h2>
          {docs.length === 0 ? (
            <div className="text-slate-500 text-sm">No documentable code chunks found.</div>
          ) : (
            <div className="space-y-4">
              {docs.map((d, i) => (
                <div key={i} className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-700">
                    <span className="text-xs font-mono text-slate-300">{d.file_path}</span>
                    <span className="text-xs text-slate-500">Lines {d.start_line}–{d.end_line}</span>
                  </div>
                  <div className="p-4 space-y-3">
                    {d.docstring && (
                      <div>
                        <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wide">Docstring</span>
                        <p className="text-sm text-slate-300 mt-1 whitespace-pre-wrap">{d.docstring}</p>
                      </div>
                    )}
                    {d.example && (
                      <div>
                        <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wide">Example</span>
                        <div className="mt-1">
                          <CodeBlock code={d.example} language="python" showLineNumbers={false} />
                        </div>
                      </div>
                    )}
                    {d.complexity && (
                      <div>
                        <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wide">Complexity</span>
                        <p className="text-sm text-slate-400 mt-1">{d.complexity}</p>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
