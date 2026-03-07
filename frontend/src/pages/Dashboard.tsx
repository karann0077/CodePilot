import { useState, useEffect } from 'react'
import { listRepos, connectRepo, deleteRepo, startIndex, type Repo } from '../api/client'

export default function Dashboard() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ name: '', git_url: '', default_branch: 'main' })
  const [error, setError] = useState('')

  const fetchRepos = async () => {
    setLoading(true)
    setError('')
    try {
      const repos = await listRepos()
      setRepos(repos)
    } catch (e: any) {
      setError(e?.userMessage || e?.response?.data?.detail || 'Failed to load repositories — check backend and CORS settings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchRepos() }, [])

  const handleConnect = async () => {
    try {
      await connectRepo(form)
      setShowModal(false)
      setForm({ name: '', git_url: '', default_branch: 'main' })
      fetchRepos()
    } catch (e: any) {
      setError(e?.userMessage || e?.response?.data?.detail || 'Failed to connect repo')
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this repo?')) return
    try { await deleteRepo(id); fetchRepos() } catch (e: any) { setError(e?.userMessage || 'Failed to delete repo') }
  }

  const handleIndex = async (id: string) => {
    try { await startIndex(id); alert('Indexing started!') } catch (e: any) { setError(e?.userMessage || 'Failed to start index') }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">CodePilot</h1>
          <p className="text-slate-400 text-sm">AI Code Companion</p>
        </div>
        <button onClick={() => setShowModal(true)} className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
          + Connect Repo
        </button>
      </div>

      {error && <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-2 rounded mb-4 text-sm">{error}</div>}

      {loading ? (
        <div className="text-slate-400">Loading repositories…</div>
      ) : repos.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          <div className="text-4xl mb-3">📦</div>
          <p>No repositories connected yet.</p>
          <button onClick={() => setShowModal(true)} className="mt-4 text-indigo-400 hover:underline text-sm">Connect your first repo →</button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {repos.map((r) => (
            <div key={r.id} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-semibold text-white">{r.name}</h3>
                <span className="text-xs bg-green-900/40 text-green-400 px-2 py-0.5 rounded">active</span>
              </div>
              <p className="text-xs text-slate-400 truncate mb-1">{r.git_url}</p>
              <p className="text-xs text-slate-500 mb-3">branch: {r.default_branch}</p>
              <div className="flex gap-2">
                <button onClick={() => handleIndex(r.id)} className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1 rounded">Index</button>
                <button onClick={() => handleDelete(r.id)} className="text-xs bg-slate-700 hover:bg-red-800 text-slate-300 px-3 py-1 rounded">Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-md">
            <h2 className="text-lg font-semibold text-white mb-4">Connect Repository</h2>
            <div className="space-y-3">
              <input placeholder="Repo name" value={form.name} onChange={e => setForm({...form, name: e.target.value})}
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
              <input placeholder="Git URL" value={form.git_url} onChange={e => setForm({...form, git_url: e.target.value})}
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
              <input placeholder="Default branch (main)" value={form.default_branch} onChange={e => setForm({...form, default_branch: e.target.value})}
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
            </div>
            <div className="flex gap-3 mt-5 justify-end">
              <button onClick={() => setShowModal(false)} className="text-sm text-slate-400 hover:text-white px-4 py-2">Cancel</button>
              <button onClick={handleConnect} className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded text-sm font-medium">Connect</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
