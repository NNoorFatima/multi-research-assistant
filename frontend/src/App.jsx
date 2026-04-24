import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from './api'

// ─── tiny helpers ────────────────────────────────────────────────────────────

function ts() {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

function IntentBadge({ intent }) {
  if (!intent) return null
  const map = {
    vague:   { label: 'VAGUE',   color: 'var(--intent-vague)'   },
    simple:  { label: 'SIMPLE',  color: 'var(--intent-simple)'  },
    complex: { label: 'COMPLEX', color: 'var(--intent-complex)' },
  }
  const { label, color } = map[intent] || {}
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600,
      letterSpacing: 2, padding: '2px 8px', borderRadius: 4,
      border: `1px solid ${color}55`, color, background: `${color}15`,
    }}>
      {label}
    </span>
  )
}

function SourcePill({ source }) {
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 10,
      padding: '2px 8px', borderRadius: 20,
      background: 'var(--bg-4)', border: '1px solid var(--border-2)',
      color: 'var(--accent)', letterSpacing: 0.5,
    }}>
      📄 {source}
    </span>
  )
}

function ThinkingIndicator() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '14px 18px',
      background: 'var(--bg-3)', borderRadius: 'var(--r-lg)', width: 'fit-content',
      border: '1px solid var(--border)', animation: 'fadeUp 0.2s ease' }}>
      <span style={{ color: 'var(--text-3)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>thinking</span>
      <span className="thinking-dot" />
      <span className="thinking-dot" />
      <span className="thinking-dot" />
    </div>
  )
}

// ─── Message bubble ──────────────────────────────────────────────────────────

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      alignItems: isUser ? 'flex-end' : 'flex-start',
      animation: 'fadeUp 0.25s ease',
      gap: 6,
    }}>
      {/* role label */}
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 2,
        color: isUser ? 'var(--accent)' : 'var(--text-3)',
        paddingLeft: isUser ? 0 : 2,
      }}>
        {isUser ? 'YOU' : 'ASSISTANT'} · {msg.time}
      </div>

      {/* bubble */}
      <div style={{
        maxWidth: '78%',
        padding: '12px 16px',
        borderRadius: isUser
          ? 'var(--r-lg) var(--r-lg) 4px var(--r-lg)'
          : 'var(--r-lg) var(--r-lg) var(--r-lg) 4px',
        background: isUser ? 'var(--accent-dim)' : 'var(--bg-3)',
        border: `1px solid ${isUser ? 'var(--accent)44' : 'var(--border)'}`,
        color: 'var(--text)',
        lineHeight: 1.7,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}>
        {msg.content}
      </div>

      {/* metadata row */}
      {!isUser && (msg.intent || (msg.sources && msg.sources.length > 0)) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', paddingLeft: 2 }}>
          {msg.intent && <IntentBadge intent={msg.intent} />}
          {(msg.sources || []).map(s => <SourcePill key={s} source={s} />)}
        </div>
      )}

      {/* clarification indicator */}
      {msg.awaiting && (
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 11,
          color: 'var(--intent-vague)', paddingLeft: 2,
        }}>
          ⌁ awaiting your reply
        </div>
      )}
    </div>
  )
}

// ─── Session item in sidebar ─────────────────────────────────────────────────

function SessionItem({ session, active, onClick, onDelete }) {
  const [hovering, setHovering] = useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      style={{
        padding: '10px 12px', borderRadius: 'var(--r)',
        background: active ? 'var(--bg-4)' : hovering ? 'var(--bg-3)' : 'transparent',
        border: `1px solid ${active ? 'var(--border-2)' : 'transparent'}`,
        cursor: 'pointer', transition: 'all 0.15s',
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        animation: 'slideIn 0.2s ease',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: active ? 'var(--text)' : 'var(--text-2)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {session.preview || 'New conversation'}
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-3)', marginTop: 2,
        }}>
          {session.turns} turn{session.turns !== 1 ? 's' : ''} · {
            session.updated_at
              ? new Date(session.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
              : ''
          }
        </div>
      </div>
      {hovering && (
        <button
          onClick={e => { e.stopPropagation(); onDelete() }}
          style={{
            background: 'var(--warn-dim)', border: '1px solid var(--warn)44',
            color: 'var(--warn)', borderRadius: 4, padding: '2px 6px',
            fontSize: 10, fontFamily: 'var(--font-mono)', marginLeft: 8, flexShrink: 0,
          }}
        >
          DEL
        </button>
      )}
    </div>
  )
}

// ─── Upload zone ─────────────────────────────────────────────────────────────

function UploadZone({ sessionId, onUploaded }) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [lastFile, setLastFile] = useState(null)
  const inputRef = useRef()

  const handleFile = useCallback(async (file) => {
    if (!file || !file.name.endsWith('.pdf')) return
    setUploading(true)
    try {
      const res = await api.upload(file, sessionId)
      setLastFile({ name: file.name, chunks: res.chunks_ingested })
      onUploaded(res)
    } catch (e) {
      console.error(e)
    } finally {
      setUploading(false)
    }
  }, [sessionId, onUploaded])

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]) }}
      onClick={() => inputRef.current?.click()}
      style={{
        border: `1.5px dashed ${dragging ? 'var(--accent)' : 'var(--border-2)'}`,
        borderRadius: 'var(--r-lg)', padding: '14px 18px',
        background: dragging ? 'var(--accent-dim)' : 'var(--bg-3)',
        cursor: uploading ? 'wait' : 'pointer',
        transition: 'all 0.2s', textAlign: 'center',
      }}
    >
      <input ref={inputRef} type="file" accept=".pdf" style={{ display: 'none' }}
        onChange={e => handleFile(e.target.files[0])} />
      {uploading ? (
        <div style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          embedding chunks<span style={{ animation: 'blink 1s infinite' }}>…</span>
        </div>
      ) : lastFile ? (
        <div style={{ color: 'var(--intent-simple)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          ✓ {lastFile.name} ({lastFile.chunks} chunks)
        </div>
      ) : (
        <div>
          <div style={{ fontSize: 20, marginBottom: 4 }}>📄</div>
          <div style={{ color: 'var(--text-2)', fontSize: 12 }}>Drop PDF or click to upload</div>
          <div style={{ color: 'var(--text-3)', fontFamily: 'var(--font-mono)', fontSize: 10, marginTop: 2 }}>
            typed PDFs only
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main App ────────────────────────────────────────────────────────────────

export default function App() {
  const [sessionId, setSessionId]     = useState(null)
  const [sessions, setSessions]       = useState([])
  const [messages, setMessages]       = useState([])
  const [input, setInput]             = useState('')
  const [loading, setLoading]         = useState(false)
  const [filterSource, setFilterSource] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [serverOk, setServerOk]       = useState(null)
  const bottomRef = useRef()
  const inputRef  = useRef()

  // ── health check on mount ──────────────────────────────────────
  useEffect(() => {
    api.health()
      .then(() => setServerOk(true))
      .catch(() => setServerOk(false))
  }, [])

  // ── load sessions list ─────────────────────────────────────────
  const refreshSessions = useCallback(async () => {
    try {
      const { sessions: list } = await api.sessions()
      setSessions(list || [])
    } catch (e) { /* server might be offline */ }
  }, [])

  useEffect(() => { refreshSessions() }, [])

  // ── auto-scroll ────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // ── load a session from sidebar ────────────────────────────────
  const loadSession = useCallback(async (sid) => {
    setSessionId(sid)
    setMessages([])
    setUploadedFiles([])
    try {
      const data = await api.history(sid)
      const rebuilt = []
      for (const msg of data.chat_history) {
        rebuilt.push({
          role: msg.role, content: msg.content,
          time: '', intent: null, sources: [], awaiting: false,
        })
      }
      setMessages(rebuilt)
    } catch (e) { console.error(e) }
  }, [])

  // ── new conversation ───────────────────────────────────────────
  const newConversation = () => {
    setSessionId(null)
    setMessages([])
    setInput('')
    setFilterSource('')
    setUploadedFiles([])
  }

  // ── delete session ────────────────────────────────────────────
  const deleteSession = useCallback(async (sid) => {
    await api.deleteSession(sid).catch(() => {})
    if (sid === sessionId) newConversation()
    await refreshSessions()
  }, [sessionId, refreshSessions])

  // ── send query ────────────────────────────────────────────────
  const sendQuery = useCallback(async () => {
    const q = input.trim()
    if (!q || loading) return

    const userMsg = { role: 'user', content: q, time: ts() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await api.query(q, sessionId, filterSource || null)
      setSessionId(res.session_id)

      const assistantMsg = {
        role: 'assistant',
        content: res.answer,
        intent: res.intent,
        sources: res.sources,
        awaiting: res.awaiting_clarification,
        time: ts(),
      }
      setMessages(prev => [...prev, assistantMsg])
      await refreshSessions()
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant', content: `Error: ${e.message}`, time: ts(),
        intent: null, sources: [], awaiting: false,
      }])
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [input, loading, sessionId, filterSource, refreshSessions])

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery() }
  }

  const onUploaded = useCallback((res) => {
    setSessionId(res.session_id)
    setUploadedFiles(prev => [...prev, res.filename])
    setMessages(prev => [...prev, {
      role: 'assistant',
      content: res.message,
      time: ts(), intent: null, sources: [], awaiting: false,
    }])
    refreshSessions()
  }, [refreshSessions])

  // ── layout ────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg)' }}>

      {/* ── Sidebar ─────────────────────────────────────────── */}
      <div style={{
        width: sidebarOpen ? 260 : 0,
        minWidth: sidebarOpen ? 260 : 0,
        overflow: 'hidden',
        transition: 'all 0.25s cubic-bezier(.4,0,.2,1)',
        borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        background: 'var(--bg-2)',
      }}>
        {/* Sidebar header */}
        <div style={{ padding: '20px 16px 12px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <div style={{
              width: 28, height: 28, borderRadius: 6,
              background: 'linear-gradient(135deg, var(--accent), var(--accent-2))',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, flexShrink: 0,
            }}>⬡</div>
            <div>
              <div style={{ fontWeight: 800, fontSize: 13, letterSpacing: 0.5 }}>LangGraph</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)', letterSpacing: 1 }}>
                × SUPABASE
              </div>
            </div>
          </div>

          {/* Server status */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            fontFamily: 'var(--font-mono)', fontSize: 10,
            color: serverOk === null ? 'var(--text-3)' : serverOk ? 'var(--intent-simple)' : 'var(--warn)',
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
              background: serverOk === null ? 'var(--text-3)' : serverOk ? 'var(--intent-simple)' : 'var(--warn)',
              boxShadow: serverOk ? '0 0 6px var(--intent-simple)' : 'none',
            }} />
            {serverOk === null ? 'connecting…' : serverOk ? 'server online' : 'server offline'}
          </div>
        </div>

        {/* New chat button */}
        <div style={{ padding: '12px 12px 6px' }}>
          <button onClick={newConversation} style={{
            width: '100%', padding: '9px 0',
            background: 'var(--accent-dim)', border: '1px solid var(--accent)44',
            borderRadius: 'var(--r)', color: 'var(--accent)',
            fontFamily: 'var(--font-ui)', fontWeight: 700, fontSize: 12, letterSpacing: 1,
            transition: 'all 0.15s',
          }}>
            + NEW CHAT
          </button>
        </div>

        {/* Session list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px' }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 2,
            color: 'var(--text-3)', padding: '8px 4px 6px', textTransform: 'uppercase',
          }}>
            History ({sessions.length})
          </div>
          {sessions.length === 0 && (
            <div style={{ color: 'var(--text-3)', fontSize: 11, padding: '8px 4px' }}>
              No sessions yet
            </div>
          )}
          {sessions.map(s => (
            <SessionItem
              key={s.session_id}
              session={s}
              active={s.session_id === sessionId}
              // onClick={() => loadSession(s.session_id)}
              onClick={() => setSessionId(s)}
              
              onDelete={() => deleteSession(s.session_id)}
            />
          ))}
        </div>
      </div>

      {/* ── Main panel ──────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>

        {/* Top bar */}
        <div style={{
          height: 52, borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', padding: '0 16px', gap: 12,
          background: 'var(--bg-2)', flexShrink: 0,
        }}>
          <button onClick={() => setSidebarOpen(v => !v)} style={{
            background: 'var(--bg-4)', border: '1px solid var(--border-2)',
            borderRadius: 6, padding: '5px 9px', color: 'var(--text-2)', fontSize: 14,
          }}>
            {sidebarOpen ? '←' : '→'}
          </button>

          <div style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)' }}>
            {sessionId
              ? <span>session <span style={{ color: 'var(--accent)' }}>{sessionId.slice(0, 8)}…</span></span>
              : <span style={{ color: 'var(--text-3)' }}>no active session</span>
            }
          </div>

          {/* Graph node flow indicator */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 4,
            fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-3)',
          }}>
            {['input','intent','decision','retrieve','answer','memory'].map((n, i) => (
              <span key={n} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {i > 0 && <span style={{ color: 'var(--border-2)' }}>›</span>}
                <span style={{
                  padding: '2px 5px', borderRadius: 3,
                  background: 'var(--bg-4)', border: '1px solid var(--border)',
                  color: loading && i === 2 ? 'var(--accent)' : 'var(--text-3)',
                }}>
                  {n}
                </span>
              </span>
            ))}
          </div>
        </div>

        {/* Messages area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 0' }}>
          <div style={{ maxWidth: 760, margin: '0 auto', padding: '0 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* Empty state */}
            {messages.length === 0 && !loading && (
              <div style={{ textAlign: 'center', padding: '48px 0', animation: 'fadeIn 0.4s ease' }}>
                <div style={{
                  width: 56, height: 56, margin: '0 auto 20px',
                  borderRadius: 16, background: 'linear-gradient(135deg, var(--accent)22, var(--accent-2)22)',
                  border: '1px solid var(--accent)33',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24,
                }}>⬡</div>
                <div style={{ fontWeight: 800, fontSize: 22, marginBottom: 8 }}>
                  LangGraph AI Assistant
                </div>
                <div style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 24 }}>
                  RAG · Graph decisions · Persistent memory
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
                  {[
                    'What is retrieval-augmented generation?',
                    'Summarise the uploaded document',
                    'What were the key findings?',
                    'Explain LangGraph to me',
                  ].map(s => (
                    <button key={s} onClick={() => setInput(s)} style={{
                      background: 'var(--bg-3)', border: '1px solid var(--border-2)',
                      borderRadius: 20, padding: '7px 14px', color: 'var(--text-2)',
                      fontSize: 12, cursor: 'pointer', transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                    onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border-2)'}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => <Message key={i} msg={msg} />)}
            {loading && <ThinkingIndicator />}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Bottom input area */}
        <div style={{
          borderTop: '1px solid var(--border)', background: 'var(--bg-2)',
          padding: '12px 16px', flexShrink: 0,
        }}>
          <div style={{ maxWidth: 760, margin: '0 auto' }}>

            {/* Upload zone + filter — shown above input */}
            <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
              {/* Upload zone */}
              <div style={{ flex: '0 0 200px' }}>
                <UploadZone sessionId={sessionId} onUploaded={onUploaded} />
              </div>

              {/* Filter + uploaded list */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', letterSpacing: 1 }}>
                  FILTER BY SOURCE (optional)
                </div>
                <input
                  value={filterSource}
                  onChange={e => setFilterSource(e.target.value)}
                  placeholder="filename.pdf"
                  style={{
                    background: 'var(--bg-3)', border: '1px solid var(--border)',
                    borderRadius: 'var(--r)', padding: '8px 12px',
                    color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 12,
                    width: '100%',
                  }}
                />
                {uploadedFiles.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {uploadedFiles.map(f => (
                      <button key={f} onClick={() => setFilterSource(f)} style={{
                        background: filterSource === f ? 'var(--accent-dim)' : 'var(--bg-4)',
                        border: `1px solid ${filterSource === f ? 'var(--accent)' : 'var(--border)'}`,
                        borderRadius: 20, padding: '2px 10px',
                        color: filterSource === f ? 'var(--accent)' : 'var(--text-3)',
                        fontFamily: 'var(--font-mono)', fontSize: 10, cursor: 'pointer',
                      }}>
                        {f}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Text input row */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Ask anything — or upload a PDF and query it…"
                rows={1}
                style={{
                  flex: 1, resize: 'none', overflowY: 'auto',
                  maxHeight: 120, minHeight: 44,
                  background: 'var(--bg-3)', border: `1px solid ${input ? 'var(--accent)66' : 'var(--border)'}`,
                  borderRadius: 'var(--r-lg)', padding: '11px 14px',
                  color: 'var(--text)', fontSize: 14, lineHeight: 1.5,
                  transition: 'border-color 0.15s',
                  fontFamily: 'var(--font-ui)',
                }}
                onInput={e => {
                  e.target.style.height = 'auto'
                  e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
                }}
              />
              <button
                onClick={sendQuery}
                disabled={loading || !input.trim()}
                style={{
                  width: 44, height: 44, borderRadius: 'var(--r-lg)',
                  background: loading || !input.trim()
                    ? 'var(--bg-4)' : 'linear-gradient(135deg, var(--accent), var(--accent-2))',
                  border: '1px solid var(--border)',
                  color: loading || !input.trim() ? 'var(--text-3)' : '#000',
                  fontSize: 18, flexShrink: 0,
                  transition: 'all 0.15s', cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                {loading
                  ? <span style={{ width: 14, height: 14, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', display: 'block', animation: 'spin 0.7s linear infinite' }} />
                  : '↑'}
              </button>
            </div>

            {/* Footer hint */}
            <div style={{
              marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 10,
              color: 'var(--text-3)', textAlign: 'center', letterSpacing: 0.5,
            }}>
              Enter to send · Shift+Enter for new line · Memory persisted to Supabase
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
