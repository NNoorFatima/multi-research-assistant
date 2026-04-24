/**
 * api.js — all HTTP calls to the FastAPI backend
 */

// const BASE = import.meta.env.VITE_API_URL || ''
const BASE = 'http://127.0.0.1:8000/api';
console.log("BASE URL:", BASE);
async function request(path, options = {}) {
  const res = await fetch(BASE + path, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  /** Send a text query */
  query(query, sessionId, filterSource) {
    return request('/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        session_id:    sessionId || undefined,
        filter_source: filterSource || undefined,
      }),
    })
  },

  /** Upload a PDF file */
  upload(file, sessionId) {
    const fd = new FormData()
    fd.append('file', file)
    if (sessionId) fd.append('session_id', sessionId)
    return request('/upload', { method: 'POST', body: fd })
  },

  /** Get history for a session */
  // history(sessionId) {
  //   return request(`/history/${sessionId}`)
  // },
  history(sessionId) {
    if (!sessionId) {
        throw new Error("sessionId is required")
      }
      return request(`/history/${sessionId}`)
  },
  /** Delete/clear a session */
  deleteSession(sessionId) {
    return request(`/history/${sessionId}`, { method: 'DELETE' })
  },

  /** List all sessions for sidebar */
  sessions() {
    return request('/sessions')
  },

  /** Health check */
  health() {
    return request('/health')
  },
}
