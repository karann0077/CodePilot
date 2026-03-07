import axios from 'axios'

// In production (Vercel), always use '/api' so Vercel's rewrite proxy in
// vercel.json forwards requests server-side to the Render backend, completely
// avoiding CORS issues. In development (`npm run dev`), fall back to
// VITE_API_URL if set (e.g. http://localhost:8000/api).
const baseURL = import.meta.env.DEV
  ? (import.meta.env.VITE_API_URL || '/api')
  : '/api'

const api = axios.create({
  baseURL,
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  response => response,
  error => {
    console.error('[API Error]', error?.config?.url, error?.response?.status, error?.response?.data)
    return Promise.reject(error)
  }
)

/**
 * Extracts a human-readable error message from an Axios error.
 * Distinguishes between CORS/network errors, server errors, and unexpected errors.
 */
export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response) {
      const detail = error.response.data?.detail || error.response.data?.message
      if (detail) return String(detail)
      return `Server error (${error.response.status})`
    } else if (error.request) {
      return 'Network error — the backend server is unreachable. If you are using a hosted frontend, verify that the backend CORS configuration includes this domain.'
    }
  }
  return 'An unexpected error occurred'
}

export interface Repo {
  id: string; name: string; git_url: string; default_branch: string;
  status: string; file_count?: number; chunk_count?: number; created_at?: string;
}
export interface IndexJob { job_id: string; status: string; progress?: number; message?: string; }
export interface Citation { file_path: string; start_line: number; end_line: number; text: string; score: number; }
export interface QueryResult { answer: string; citations: Citation[]; cached: boolean; }
export interface Suspect { file_path: string; start_line: number; end_line: number; probability: number; explanation: string; }
export interface DiagnoseResult { suspects: Suspect[]; }
export interface Hunk { header: string; lines: string[]; }
export interface PatchResult { patch_id: string; target_file: string; hunks: Hunk[]; raw_diff: string; explanation: string; unit_test: string; confidence: number; }
export interface TestResult { name: string; status: string; duration_ms: number; message: string; }
export interface SandboxResult { job_id: string; status: string; stdout: string; stderr: string; test_results: TestResult[]; confidence: number; }
export interface ConfidenceEvidence { component: string; score: number; weight: number; details: string; }
export interface ConfidenceResult { score: number; evidence: ConfidenceEvidence[]; }
export interface DocGenJob { job_id: string; status: string; }
export interface DocEntry { chunk_id: string; file_path: string; start_line: number; end_line: number; docstring: string; example: string; complexity: string; }
export interface DocGenResult { job_id: string; status: string; doc_count?: number; docs?: DocEntry[]; error?: string; }

export const connectRepo = (data: { name: string; git_url: string; default_branch?: string }) =>
  api.post<Repo>('/repos/connect', data).then(r => r.data)
export const listRepos = () => api.get<Repo[]>('/repos').then(r => r.data)
export const deleteRepo = (id: string) => api.delete(`/repos/${id}`).then(r => r.data)
export const startIndex = (repo_id: string) => api.post<IndexJob>('/index/start', { repo_id }).then(r => r.data)
export const getIndexStatus = (job_id: string) => api.get<IndexJob>(`/index/status/${job_id}`).then(r => r.data)
export const query = (data: { repo_id: string; question: string; top_k?: number }) =>
  api.post<QueryResult>('/query', data).then(r => r.data)
export const diagnose = (data: { repo_id: string; error_text: string; stacktrace?: string }) =>
  api.post<DiagnoseResult>('/diagnose', data).then(r => r.data)
export const proposePatch = (data: { repo_id: string; issue_description: string; file_path?: string }) =>
  api.post<PatchResult>('/patch/propose', data).then(r => r.data)
export const runSandbox = (data: { patch_id: string; repo_id: string }) =>
  api.post<SandboxResult>('/sandbox/run', data).then(r => r.data)
export const getSandboxResult = (job_id: string) => api.get<SandboxResult>(`/sandbox/result/${job_id}`).then(r => r.data)
export const generateDocs = (data: { repo_id: string; file_path?: string }) =>
  api.post<DocGenJob>('/docs_gen/generate', data).then(r => r.data)
export const getDocResult = (job_id: string) =>
  api.get<DocGenResult>(`/docs_gen/result/${job_id}`).then(r => r.data)

export default api
