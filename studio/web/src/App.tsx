import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  Activity,
  Archive,
  BookOpen,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  CloudUpload,
  Code2,
  FileArchive,
  FileCode2,
  FileText,
  FolderOpen,
  Gauge,
  Image,
  Languages,
  Library,
  ListChecks,
  LoaderCircle,
  Menu,
  MessageSquareText,
  MoreHorizontal,
  PanelRightClose,
  PanelRightOpen,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  ScanSearch,
  Search,
  Send,
  Settings,
  Sparkles,
  Square,
  Terminal,
  Upload,
  WandSparkles,
  X,
} from 'lucide-react'

type Workflow = 'lingualeaf' | 'pocket_exact' | 'pocket_polished' | 'custom'
type View = 'workspace' | 'library' | 'jobs' | 'settings'
type Profile = 'auto' | 'fast' | 'balanced' | 'deep' | 'ultra'

type Project = {
  id: string
  slug: string
  title: string
  workflow: Workflow
  book_id: string
  source_language: string
  primary_language: string
  target_languages: string[]
  status: string
  sources?: Source[]
  jobs?: Job[]
  artifacts?: Artifact[]
  messages?: ChatMessage[]
  pipeline?: Pipeline
}

type Source = {
  id: string
  path: string
  role: string
  language: string
  media_type: string
  size_bytes: number
}

type Evidence = {
  id: string
  label: string
  passed: number | boolean
  detail: string
}

type Job = {
  id: string
  project_id: string
  capability_id: string
  title: string
  status: string
  progress: number
  tmux_session: string
  log_path: string
  error: string
  created_at: string
  started_at?: string
  finished_at?: string
  evidence?: Evidence[]
}

type Artifact = {
  id: string
  kind: string
  label: string
  path: string
}

type ChatMessage = {
  id?: string
  role: 'user' | 'assistant'
  content: string
  model?: string
  reasoning?: string
  pending?: boolean
}

type PipelineStage = {
  id: string
  title: string
  argv: string[]
  acceptance: unknown[]
}

type Pipeline = {
  schema_version: number
  stages: PipelineStage[]
}

type Capability = {
  id: string
  name: string
  category: string
  description: string
  workflows: Workflow[]
  icon: string
  parameters: Array<{ name: string; type: string; default?: unknown; required?: boolean }>
}

type DiscoveredBook = {
  book_id: string
  title: string
  workflow: Workflow
  generated: number
  total: number
  pdf_count: number
  complete: boolean
  cover: string
}

type RepositoryState = {
  books: DiscoveredBook[]
  counts: { books: number; complete: number; in_progress: number; pdfs: number }
}

type Health = {
  status: string
  version: string
  repo_root: string
  state_root: string
  chat_model: string
  default_reasoning: string
  codex_version: string
  tools: Record<string, { available: boolean; path: string }>
}

const WORKFLOW_LABELS: Record<Workflow, string> = {
  lingualeaf: 'LinguaLeaf',
  pocket_exact: 'Exact TeX',
  pocket_polished: 'PocketPolished',
  custom: 'Custom',
}

const PROFILE_LABELS: Array<{ id: Profile; label: string; hint: string }> = [
  { id: 'auto', label: 'Auto', hint: 'Route by task' },
  { id: 'fast', label: 'Fast', hint: 'Low reasoning' },
  { id: 'deep', label: 'Deep', hint: 'High reasoning' },
  { id: 'ultra', label: 'Ultra', hint: 'X-high audit' },
]

const ACTIVE_STATUSES = new Set(['launching', 'running', 'cancelling'])

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}`
}

function relativeTime(value?: string): string {
  if (!value) return 'not started'
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

function statusTone(status: string): string {
  if (status === 'complete' || status === 'ready') return 'positive'
  if (ACTIVE_STATUSES.has(status) || status === 'active') return 'active'
  if (status === 'blocked' || status === 'failed' || status === 'attention' || status === 'interrupted') return 'negative'
  return 'neutral'
}

function StatusMark({ status }: { status: string }) {
  const tone = statusTone(status)
  const Icon = tone === 'positive' ? CheckCircle2 : tone === 'negative' ? CircleAlert : tone === 'active' ? LoaderCircle : Clock3
  return (
    <span className={`status-mark ${tone}`}>
      <Icon size={14} className={tone === 'active' ? 'spin' : ''} />
      {status.replaceAll('_', ' ')}
    </span>
  )
}

function App() {
  const [view, setView] = useState<View>('workspace')
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedId, setSelectedId] = useState<string>('')
  const [project, setProject] = useState<Project | null>(null)
  const [repository, setRepository] = useState<RepositoryState | null>(null)
  const [capabilities, setCapabilities] = useState<Capability[]>([])
  const [allJobs, setAllJobs] = useState<Job[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [chatOpen, setChatOpen] = useState(() => window.innerWidth > 900)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [jobDetail, setJobDetail] = useState<Job | null>(null)
  const [jobLog, setJobLog] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const refreshGlobal = useCallback(async () => {
    try {
      const [projectList, repoState, capabilityList, jobsList, healthState] = await Promise.all([
        api<Project[]>('/api/projects'),
        api<RepositoryState>('/api/repository'),
        api<Capability[]>('/api/capabilities'),
        api<Job[]>('/api/jobs?limit=150'),
        api<Health>('/api/health'),
      ])
      setProjects(projectList)
      setRepository(repoState)
      setCapabilities(capabilityList)
      setAllJobs(jobsList)
      setHealth(healthState)
      if (!selectedId && projectList.length) setSelectedId(projectList[0].id)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }, [selectedId])

  const refreshProject = useCallback(async () => {
    if (!selectedId) {
      setProject(null)
      return
    }
    try {
      setProject(await api<Project>(`/api/projects/${selectedId}`))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }, [selectedId])

  useEffect(() => {
    void refreshGlobal()
  }, [refreshGlobal])

  useEffect(() => {
    void refreshProject()
  }, [refreshProject])

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshGlobal()
      void refreshProject()
    }, 6000)
    return () => window.clearInterval(timer)
  }, [refreshGlobal, refreshProject])

  async function importBook(book: DiscoveredBook) {
    setBusy(true)
    setError('')
    try {
      const imported = await api<Project>(`/api/projects/import/${encodeURIComponent(book.book_id)}`, { method: 'POST' })
      await refreshGlobal()
      setSelectedId(imported.id)
      setView('workspace')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function launchCapability(capabilityId: string, parameters: Record<string, unknown> = {}) {
    if (!project) return
    setBusy(true)
    setError('')
    try {
      const job = await api<Job>(`/api/projects/${project.id}/jobs`, {
        method: 'POST',
        body: JSON.stringify({ capability_id: capabilityId, parameters }),
      })
      setJobDetail(job)
      await Promise.all([refreshProject(), refreshGlobal()])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function inspectJob(job: Job) {
    try {
      const detail = await api<Job>(`/api/jobs/${job.id}`)
      const log = await fetch(`/api/jobs/${job.id}/log?tail=500`).then((response) => response.text())
      setJobDetail(detail)
      setJobLog(log)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  async function cancelJob(job: Job) {
    await api(`/api/jobs/${job.id}/cancel`, { method: 'POST' })
    await Promise.all([refreshProject(), refreshGlobal()])
    setJobDetail(null)
  }

  async function retryJob(job: Job) {
    const retried = await api<Job>(`/api/jobs/${job.id}/retry`, { method: 'POST' })
    setJobDetail(retried)
    await Promise.all([refreshProject(), refreshGlobal()])
  }

  const activeJobs = allJobs.filter((job) => ACTIVE_STATUSES.has(job.status))

  return (
    <div className={`app-shell ${chatOpen ? 'with-chat' : ''}`}>
      <aside className={`sidebar ${sidebarOpen ? 'mobile-open' : ''}`}>
        <div className="brand-row">
          <div className="brand-mark">文</div>
          <div className="brand-copy">
            <strong>PocketPolyglot</strong>
            <span>Studio</span>
          </div>
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(false)} aria-label="Close navigation">
            <X size={19} />
          </button>
        </div>

        <nav className="primary-nav" aria-label="Studio navigation">
          <NavButton active={view === 'workspace'} icon={<Sparkles />} label="Workspace" onClick={() => setView('workspace')} />
          <NavButton active={view === 'library'} icon={<Library />} label="Library" count={repository?.counts.books} onClick={() => setView('library')} />
          <NavButton active={view === 'jobs'} icon={<Activity />} label="Jobs" count={activeJobs.length || undefined} onClick={() => setView('jobs')} />
          <NavButton active={view === 'settings'} icon={<Settings />} label="Runtime" onClick={() => setView('settings')} />
        </nav>

        <div className="sidebar-heading">
          <span>Projects</span>
          <button className="icon-button" onClick={() => setCreateOpen(true)} title="New project" aria-label="New project">
            <Plus size={17} />
          </button>
        </div>
        <div className="project-list">
          {projects.map((item) => (
            <button
              className={`project-row ${selectedId === item.id ? 'selected' : ''}`}
              key={item.id}
              onClick={() => {
                setSelectedId(item.id)
                setView('workspace')
                setSidebarOpen(false)
              }}
            >
              <span className={`project-dot ${statusTone(item.status)}`} />
              <span className="project-row-copy">
                <strong>{item.title}</strong>
                <span>{WORKFLOW_LABELS[item.workflow]}</span>
              </span>
              <ChevronRight size={15} />
            </button>
          ))}
          {!projects.length && <p className="empty-sidebar">Import a book or create a project.</p>}
        </div>
        <div className="sidebar-runtime">
          <Bot size={16} />
          <div>
            <strong>{health?.chat_model || 'Codex'}</strong>
            <span>{health?.default_reasoning || 'low'} default</span>
          </div>
          <span className={`runtime-light ${health?.status === 'ok' ? 'online' : ''}`} />
        </div>
      </aside>

      <main className="main-column">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)} aria-label="Open navigation">
            <Menu size={20} />
          </button>
          <div className="breadcrumbs">
            <span>{view === 'workspace' ? 'Studio' : view[0].toUpperCase() + view.slice(1)}</span>
            {view === 'workspace' && project && <><ChevronRight size={15} /><strong>{project.title}</strong></>}
          </div>
          <div className="topbar-actions">
            <button className="icon-button" onClick={() => { void refreshGlobal(); void refreshProject() }} title="Refresh" aria-label="Refresh">
              <RefreshCw size={17} />
            </button>
            <button className={`command-button ${chatOpen ? 'active' : ''}`} onClick={() => setChatOpen((open) => !open)}>
              {chatOpen ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}
              <span>Codex</span>
            </button>
          </div>
        </header>

        {error && (
          <div className="error-banner" role="alert">
            <CircleAlert size={17} />
            <span>{error}</span>
            <button className="icon-button" onClick={() => setError('')} aria-label="Dismiss error"><X size={16} /></button>
          </div>
        )}

        <div className="page-content">
          {view === 'workspace' && (
            project ? (
              <Workspace
                project={project}
                capabilities={capabilities}
                busy={busy}
                launchCapability={launchCapability}
                inspectJob={inspectJob}
                refresh={refreshProject}
              />
            ) : (
              <EmptyWorkspace repository={repository} importBook={importBook} createProject={() => setCreateOpen(true)} busy={busy} />
            )
          )}
          {view === 'library' && <LibraryView repository={repository} projects={projects} importBook={importBook} busy={busy} />}
          {view === 'jobs' && <JobsView jobs={allJobs} projects={projects} inspectJob={inspectJob} />}
          {view === 'settings' && <RuntimeView health={health} />}
        </div>
      </main>

      {chatOpen && project && <ChatPanel project={project} onClose={() => setChatOpen(false)} onRefresh={refreshProject} />}

      {createOpen && (
        <CreateProjectModal
          onClose={() => setCreateOpen(false)}
          onCreated={async (created) => {
            setCreateOpen(false)
            await refreshGlobal()
            setSelectedId(created.id)
            setView('workspace')
          }}
        />
      )}

      {jobDetail && (
        <JobDrawer
          job={jobDetail}
          log={jobLog}
          onClose={() => { setJobDetail(null); setJobLog('') }}
          onRefresh={() => inspectJob(jobDetail)}
          onCancel={() => cancelJob(jobDetail)}
          onRetry={() => retryJob(jobDetail)}
        />
      )}
    </div>
  )
}

function NavButton({ active, icon, label, count, onClick }: { active: boolean; icon: React.ReactNode; label: string; count?: number; onClick: () => void }) {
  return (
    <button className={`nav-button ${active ? 'active' : ''}`} onClick={onClick}>
      {icon}
      <span>{label}</span>
      {count !== undefined && <b>{count}</b>}
    </button>
  )
}

function Workspace({ project, capabilities, busy, launchCapability, inspectJob, refresh }: {
  project: Project
  capabilities: Capability[]
  busy: boolean
  launchCapability: (id: string, parameters?: Record<string, unknown>) => Promise<void>
  inspectJob: (job: Job) => Promise<void>
  refresh: () => Promise<void>
}) {
  const [sourcePath, setSourcePath] = useState('')
  const [sourceLanguage, setSourceLanguage] = useState(project.source_language)
  const [adding, setAdding] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const projectCapabilities = capabilities.filter((item) => item.workflows.includes(project.workflow) && !['pipeline.stage', 'custom.command'].includes(item.id))
  const jobs = project.jobs || []
  const active = jobs.filter((job) => ACTIVE_STATUSES.has(job.status))

  async function addSource(event: FormEvent) {
    event.preventDefault()
    if (!sourcePath.trim()) return
    setAdding(true)
    try {
      await api(`/api/projects/${project.id}/sources`, {
        method: 'POST',
        body: JSON.stringify({ path: sourcePath, language: sourceLanguage, role: 'reference' }),
      })
      setSourcePath('')
      await refresh()
    } finally {
      setAdding(false)
    }
  }

  async function uploadFile(file?: File) {
    if (!file) return
    setAdding(true)
    try {
      const response = await fetch(`/api/projects/${project.id}/uploads/${encodeURIComponent(file.name)}`, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file.type || 'application/octet-stream', 'X-Source-Language': sourceLanguage },
      })
      if (!response.ok) throw new Error(await response.text())
      await refresh()
    } finally {
      setAdding(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  return (
    <div className="workspace-page">
      <section className="project-hero">
        <div className="cover-frame">
          <img src={`/api/covers/${encodeURIComponent(project.book_id)}`} alt="" onError={(event) => { event.currentTarget.style.display = 'none' }} />
          <BookOpen size={34} />
        </div>
        <div className="project-identity">
          <div className="eyebrow-row">
            <span className="workflow-label">{WORKFLOW_LABELS[project.workflow]}</span>
            <StatusMark status={project.status} />
          </div>
          <h1>{project.title}</h1>
          <p className="language-line">
            <strong>{project.primary_language === 'wenyan' ? '文言文' : project.primary_language.toUpperCase()}</strong>
            <ChevronRight size={15} />
            {project.target_languages.map((language) => <span key={language}>{language.toUpperCase()}</span>)}
          </p>
          <div className="project-meta">
            <span><FolderOpen size={15} /> books/{project.book_id}</span>
            <span><ListChecks size={15} /> {project.pipeline?.stages?.length || 0} stages</span>
            <span><Activity size={15} /> {active.length} active</span>
          </div>
        </div>
        <button className="primary-button" disabled={busy} onClick={() => launchCapability('source.inspect')}>
          <ScanSearch size={17} /> Inspect sources
        </button>
      </section>

      <section className="workspace-section">
        <div className="section-title-row">
          <div>
            <span className="section-kicker">Inputs</span>
            <h2>Source library</h2>
          </div>
          <span className="section-count">{project.sources?.length || 0} registered</span>
        </div>
        <div className="source-grid">
          {(project.sources || []).map((source) => (
            <div className="source-item" key={source.id}>
              <div className="file-icon">{source.media_type.includes('pdf') ? <FileText /> : source.media_type.includes('epub') ? <FileArchive /> : <FileCode2 />}</div>
              <div className="source-copy">
                <strong title={source.path}>{source.path.split('/').at(-1)}</strong>
                <span>{source.language || 'unclassified'} · {source.role} · {formatBytes(source.size_bytes)}</span>
                <small>{source.path}</small>
              </div>
              <Check size={17} className="source-ok" />
            </div>
          ))}
          {!project.sources?.length && <div className="empty-inline"><Archive size={22} /><span>No source files registered yet.</span></div>}
        </div>
        <form className="source-add-row" onSubmit={addSource}>
          <input value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="/absolute/path/to/book.pdf or .epub" aria-label="Local source path" />
          <select value={sourceLanguage} onChange={(event) => setSourceLanguage(event.target.value)} aria-label="Source language">
            {['en', 'ja', 'zh', 'wenyan', 'ar', 'other'].map((language) => <option key={language} value={language}>{language === 'wenyan' ? '文言文' : language.toUpperCase()}</option>)}
          </select>
          <button className="secondary-button" disabled={adding || !sourcePath.trim()}><Plus size={16} /> Register</button>
          <input ref={fileInput} type="file" hidden onChange={(event) => void uploadFile(event.target.files?.[0])} />
          <button type="button" className="icon-button bordered" title="Upload source" aria-label="Upload source" onClick={() => fileInput.current?.click()} disabled={adding}>
            <Upload size={17} />
          </button>
        </form>
      </section>

      <section className="workspace-section">
        <div className="section-title-row">
          <div>
            <span className="section-kicker">Execution</span>
            <h2>Pipeline</h2>
          </div>
          <span className="section-count">Evidence-gated</span>
        </div>
        <div className="pipeline-list">
          {(project.pipeline?.stages || []).map((stage, index) => {
            const stageJobs = jobs.filter((job) => job.capability_id === 'pipeline.stage' && job.title === stage.title)
            const latest = stageJobs[0]
            return (
              <div className="pipeline-row" key={stage.id}>
                <span className="stage-number">{String(index + 1).padStart(2, '0')}</span>
                <div className="stage-main">
                  <strong>{stage.title}</strong>
                  <span>{stage.argv.slice(0, 5).join(' ')}{stage.argv.length > 5 ? ' …' : ''}</span>
                </div>
                {latest ? <StatusMark status={latest.status} /> : <span className="stage-ready">Ready</span>}
                <button className="icon-button bordered" onClick={() => launchCapability('pipeline.stage', { stage_id: stage.id })} disabled={busy || (latest && ACTIVE_STATUSES.has(latest.status))} title={`Run ${stage.title}`} aria-label={`Run ${stage.title}`}>
                  <Play size={16} />
                </button>
              </div>
            )
          })}
          {!project.pipeline?.stages?.length && <div className="empty-inline"><ListChecks size={22} /><span>Run Prepare with Codex to create the executable project pipeline.</span></div>}
        </div>
      </section>

      <section className="workspace-section">
        <div className="section-title-row">
          <div>
            <span className="section-kicker">Tools</span>
            <h2>Capabilities</h2>
          </div>
        </div>
        <div className="capability-grid">
          {projectCapabilities.map((capability) => (
            <button
              className="capability-item"
              key={capability.id}
              onClick={() => {
                const parameters = Object.fromEntries(capability.parameters.filter((parameter) => parameter.default !== undefined).map((parameter) => [parameter.name, parameter.default]))
                void launchCapability(capability.id, parameters)
              }}
              disabled={busy}
            >
              <CapabilityIcon id={capability.icon} />
              <span><strong>{capability.name}</strong><small>{capability.description}</small></span>
              <ChevronRight size={16} />
            </button>
          ))}
        </div>
      </section>

      <section className="workspace-section">
        <div className="section-title-row">
          <div>
            <span className="section-kicker">Runtime</span>
            <h2>Recent jobs</h2>
          </div>
          <span className="section-count">tmux persistent</span>
        </div>
        <JobTable jobs={jobs.slice(0, 12)} onSelect={inspectJob} />
      </section>

      <section className="workspace-section">
        <div className="section-title-row">
          <div>
            <span className="section-kicker">Outputs</span>
            <h2>Artifacts</h2>
          </div>
          <span className="section-count">{project.artifacts?.length || 0} verified</span>
        </div>
        <div className="artifact-list">
          {(project.artifacts || []).map((artifact) => (
            <a className="artifact-row" key={artifact.id} href={`/api/files?path=${encodeURIComponent(artifact.path)}`} target="_blank" rel="noreferrer">
              {artifact.kind === 'pdf' ? <FileText size={18} /> : artifact.kind === 'image' ? <Image size={18} /> : <FileCode2 size={18} />}
              <span><strong>{artifact.label}</strong><small>{artifact.path}</small></span>
              <ChevronRight size={16} />
            </a>
          ))}
          {!project.artifacts?.length && <div className="empty-inline"><FileText size={22} /><span>Accepted files appear here after evidence checks pass.</span></div>}
        </div>
      </section>
    </div>
  )
}

function CapabilityIcon({ id }: { id: string }) {
  const props = { size: 21 }
  if (id === 'scan-search') return <ScanSearch {...props} />
  if (id === 'wand-sparkles') return <WandSparkles {...props} />
  if (id === 'languages') return <Languages {...props} />
  if (id === 'file-code-2') return <FileCode2 {...props} />
  if (id === 'cloud-upload') return <CloudUpload {...props} />
  if (id === 'image') return <Image {...props} />
  if (id === 'shield-check') return <CheckCircle2 {...props} />
  if (id === 'terminal') return <Terminal {...props} />
  if (id === 'book-open-check') return <BookOpen {...props} />
  return <Sparkles {...props} />
}

function JobTable({ jobs, onSelect }: { jobs: Job[]; onSelect: (job: Job) => void }) {
  if (!jobs.length) return <div className="empty-inline"><Activity size={22} /><span>No jobs have run in this scope.</span></div>
  return (
    <div className="job-table">
      <div className="job-table-head"><span>Job</span><span>Status</span><span>Started</span><span /></div>
      {jobs.map((job) => (
        <button className="job-table-row" key={job.id} onClick={() => onSelect(job)}>
          <span className="job-title"><strong>{job.title}</strong><small>{job.capability_id}</small></span>
          <StatusMark status={job.status} />
          <span className="job-time">{relativeTime(job.started_at || job.created_at)}</span>
          <MoreHorizontal size={17} />
        </button>
      ))}
    </div>
  )
}

function EmptyWorkspace({ repository, importBook, createProject, busy }: { repository: RepositoryState | null; importBook: (book: DiscoveredBook) => void; createProject: () => void; busy: boolean }) {
  const suggestions = repository?.books.slice(0, 5) || []
  return (
    <div className="empty-workspace">
      <div className="empty-symbol"><Languages size={38} /></div>
      <h1>Open a book workflow</h1>
      <p>Create a new LinguaLeaf or TeX project, or import one of the repository’s existing books into the Studio.</p>
      <div className="empty-actions"><button className="primary-button" onClick={createProject}><Plus size={17} /> New project</button></div>
      <div className="suggestion-list">
        {suggestions.map((book) => <button key={book.book_id} onClick={() => importBook(book)} disabled={busy}><BookOpen size={17} /><span>{book.title}</span><ChevronRight size={16} /></button>)}
      </div>
    </div>
  )
}

function LibraryView({ repository, projects, importBook, busy }: { repository: RepositoryState | null; projects: Project[]; importBook: (book: DiscoveredBook) => void; busy: boolean }) {
  const [query, setQuery] = useState('')
  const imported = new Set(projects.map((project) => project.book_id))
  const books = (repository?.books || []).filter((book) => `${book.title} ${book.book_id}`.toLowerCase().includes(query.toLowerCase()))
  return (
    <div className="standard-page">
      <div className="page-heading">
        <div><span className="section-kicker">Repository</span><h1>Book library</h1><p>Live manifest coverage and output evidence from the current workspace.</p></div>
        <label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search books" /></label>
      </div>
      <div className="metric-strip">
        <Metric label="Discovered" value={repository?.counts.books || 0} icon={<Library />} />
        <Metric label="Complete" value={repository?.counts.complete || 0} icon={<CheckCircle2 />} />
        <Metric label="In progress" value={repository?.counts.in_progress || 0} icon={<Activity />} />
        <Metric label="PDF outputs" value={repository?.counts.pdfs || 0} icon={<FileText />} />
      </div>
      <div className="library-grid">
        {books.map((book) => {
          const percent = book.total ? Math.round((book.generated / book.total) * 100) : book.complete ? 100 : 0
          return (
            <article className="book-card" key={book.book_id}>
              <div className="book-cover-mini">
                {book.cover && <img src={`/api/covers/${encodeURIComponent(book.book_id)}`} alt="" />}
                <BookOpen size={26} />
              </div>
              <div className="book-card-copy">
                <span className="workflow-label">{WORKFLOW_LABELS[book.workflow]}</span>
                <h3>{book.title}</h3>
                <p>{book.generated}/{book.total || '—'} chunks · {book.pdf_count} PDFs</p>
                <div className="progress-track"><span style={{ width: `${Math.min(percent, 100)}%` }} /></div>
              </div>
              {imported.has(book.book_id) ? <span className="imported-mark"><Check size={15} /> Open</span> : <button className="secondary-button" disabled={busy} onClick={() => importBook(book)}>Import</button>}
            </article>
          )
        })}
      </div>
    </div>
  )
}

function Metric({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return <div className="metric-item"><span>{icon}</span><div><strong>{value}</strong><small>{label}</small></div></div>
}

function JobsView({ jobs, projects, inspectJob }: { jobs: Job[]; projects: Project[]; inspectJob: (job: Job) => void }) {
  const byId = new Map(projects.map((project) => [project.id, project]))
  return (
    <div className="standard-page">
      <div className="page-heading"><div><span className="section-kicker">Runtime</span><h1>Durable jobs</h1><p>Every command runs independently in tmux and closes only after acceptance evidence is evaluated.</p></div></div>
      <div className="jobs-full-list">
        {jobs.map((job) => (
          <button className="jobs-full-row" key={job.id} onClick={() => inspectJob(job)}>
            <div className={`job-state-icon ${statusTone(job.status)}`}>{ACTIVE_STATUSES.has(job.status) ? <LoaderCircle className="spin" /> : job.status === 'complete' ? <CheckCircle2 /> : <Terminal />}</div>
            <div className="jobs-full-main"><strong>{job.title}</strong><span>{byId.get(job.project_id)?.title || 'Repository'} · {job.capability_id}</span></div>
            <StatusMark status={job.status} />
            <span className="job-time">{relativeTime(job.started_at || job.created_at)}</span>
            <ChevronRight size={17} />
          </button>
        ))}
        {!jobs.length && <div className="empty-inline"><Activity size={24} /><span>No Studio jobs yet.</span></div>}
      </div>
    </div>
  )
}

function RuntimeView({ health }: { health: Health | null }) {
  return (
    <div className="standard-page">
      <div className="page-heading"><div><span className="section-kicker">System</span><h1>Runtime</h1><p>Local dependencies and the model policy used by Studio chat and workers.</p></div></div>
      <section className="runtime-band">
        <div className="runtime-model"><Bot size={28} /><div><span>Default chat</span><strong>{health?.chat_model || '—'}</strong><small>{health?.default_reasoning || '—'} reasoning · automatic escalation available</small></div></div>
        <div className="runtime-paths"><span><strong>Repository</strong>{health?.repo_root}</span><span><strong>State</strong>{health?.state_root}</span><span><strong>CLI</strong>{health?.codex_version}</span></div>
      </section>
      <section className="workspace-section">
        <div className="section-title-row"><div><span className="section-kicker">Dependencies</span><h2>Toolchain</h2></div></div>
        <div className="tool-grid">
          {Object.entries(health?.tools || {}).map(([name, tool]) => <div className="tool-row" key={name}><Code2 size={18} /><strong>{name}</strong><span>{tool.path}</span>{tool.available ? <CheckCircle2 size={17} className="source-ok" /> : <CircleAlert size={17} className="danger-icon" />}</div>)}
        </div>
      </section>
    </div>
  )
}

function ChatPanel({ project, onClose, onRefresh }: { project: Project; onClose: () => void; onRefresh: () => Promise<void> }) {
  const [messages, setMessages] = useState<ChatMessage[]>(project.messages || [])
  const [draft, setDraft] = useState('')
  const [profile, setProfile] = useState<Profile>('auto')
  const [agentMode, setAgentMode] = useState(true)
  const [sending, setSending] = useState(false)
  const [route, setRoute] = useState('gpt-5.6-sol · low')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => setMessages(project.messages || []), [project.id, project.messages])
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }) }, [messages])

  async function sendMessage(event: FormEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || sending) return
    setDraft('')
    setSending(true)
    const user: ChatMessage = { role: 'user', content: text }
    const assistant: ChatMessage = { role: 'assistant', content: '', pending: true }
    setMessages((current) => [...current, user, assistant])
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: project.id, message: text, profile, agent_mode: agentMode }),
      })
      if (!response.ok || !response.body) throw new Error(await response.text())
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        buffer = frames.pop() || ''
        for (const frame of frames) {
          const line = frame.split('\n').find((entry) => entry.startsWith('data: '))
          if (!line) continue
          const payload = JSON.parse(line.slice(6))
          if (payload.type === 'route') setRoute(`${payload.model} · ${payload.reasoning}`)
          if (payload.type === 'message') {
            setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, content: `${item.content}${item.content ? '\n\n' : ''}${payload.text}`, pending: true } : item))
          }
          if (payload.type === 'error') {
            setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, content: payload.text, pending: false } : item))
          }
        }
      }
      setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, pending: false } : item))
      await onRefresh()
    } catch (reason) {
      setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, content: reason instanceof Error ? reason.message : String(reason), pending: false } : item))
    } finally {
      setSending(false)
    }
  }

  return (
    <aside className="chat-panel">
      <div className="chat-header">
        <div className="chat-avatar"><Bot size={20} /></div>
        <div><strong>Studio Codex</strong><span>{route}</span></div>
        <button className="icon-button" onClick={onClose} aria-label="Close chat"><X size={18} /></button>
      </div>
      <div className="profile-control" aria-label="Reasoning profile">
        {PROFILE_LABELS.map((item) => <button key={item.id} className={profile === item.id ? 'active' : ''} onClick={() => setProfile(item.id)} title={item.hint}>{item.label}</button>)}
      </div>
      <div className="chat-context"><BookOpen size={15} /><span>{project.title}</span><label><input type="checkbox" checked={agentMode} onChange={(event) => setAgentMode(event.target.checked)} /> Agent</label></div>
      <div className="chat-messages" ref={scrollRef}>
        {!messages.length && <div className="chat-welcome"><Sparkles size={24} /><strong>Work in this project</strong><p>Ask Codex to inspect sources, prepare manifests, diagnose a stalled queue, compile an edition, or verify an artifact.</p></div>}
        {messages.map((message, index) => (
          <div className={`chat-message ${message.role}`} key={message.id || index}>
            <span className="message-role">{message.role === 'user' ? 'You' : 'Codex'}</span>
            <div className="message-body"><ReactMarkdown>{message.content || (message.pending ? 'Working…' : '')}</ReactMarkdown>{message.pending && <LoaderCircle size={15} className="spin message-spinner" />}</div>
          </div>
        ))}
      </div>
      <form className="chat-composer" onSubmit={sendMessage}>
        <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit() } }} placeholder="Ask Codex to work on this book…" rows={3} />
        <div><span>{agentMode ? 'Workspace access' : 'Read only'}</span><button className="send-button" disabled={sending || !draft.trim()} aria-label="Send"><Send size={17} /></button></div>
      </form>
    </aside>
  )
}

function CreateProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: (project: Project) => void }) {
  const [title, setTitle] = useState('')
  const [workflow, setWorkflow] = useState<Workflow>('lingualeaf')
  const [sourceLanguage, setSourceLanguage] = useState('en')
  const [primaryLanguage, setPrimaryLanguage] = useState('en')
  const [targets, setTargets] = useState(['ja', 'zh'])
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      const created = await api<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ title, workflow, source_language: sourceLanguage, primary_language: primaryLanguage, target_languages: targets }) })
      onCreated(created)
    } finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <form className="modal-panel" onSubmit={submit}>
        <div className="modal-header"><div><span className="section-kicker">New project</span><h2>Choose a workflow</h2></div><button type="button" className="icon-button" onClick={onClose}><X size={18} /></button></div>
        <label className="field-label">Title<input autoFocus required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Book or project title" /></label>
        <div className="workflow-picker">
          {([
            ['lingualeaf', Languages, 'Multilingual aligned book'],
            ['pocket_exact', FileCode2, 'PDF to exact and pocket TeX'],
            ['pocket_polished', Sparkles, 'Lossless TeX polish'],
            ['custom', Terminal, 'Custom repository workflow'],
          ] as const).map(([id, Icon, description]) => <button type="button" key={id} className={workflow === id ? 'selected' : ''} onClick={() => setWorkflow(id)}><Icon size={20} /><strong>{WORKFLOW_LABELS[id]}</strong><span>{description}</span></button>)}
        </div>
        <div className="field-grid">
          <label className="field-label">Source language<select value={sourceLanguage} onChange={(event) => { setSourceLanguage(event.target.value); setPrimaryLanguage(event.target.value) }}>{['en', 'ja', 'zh', 'wenyan', 'ar'].map((value) => <option key={value} value={value}>{value === 'wenyan' ? '文言文' : value.toUpperCase()}</option>)}</select></label>
          <label className="field-label">Main text<select value={primaryLanguage} onChange={(event) => setPrimaryLanguage(event.target.value)}>{['en', 'ja', 'zh', 'wenyan', 'ar'].map((value) => <option key={value} value={value}>{value === 'wenyan' ? '文言文' : value.toUpperCase()}</option>)}</select></label>
        </div>
        <fieldset className="target-picker"><legend>Secondary languages</legend>{['en', 'ja', 'zh'].map((language) => <label key={language}><input type="checkbox" checked={targets.includes(language)} onChange={(event) => setTargets((current) => event.target.checked ? [...new Set([...current, language])] : current.filter((value) => value !== language))} /><span>{language.toUpperCase()}</span></label>)}</fieldset>
        <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={!title.trim() || busy}>{busy ? <LoaderCircle size={17} className="spin" /> : <Plus size={17} />} Create project</button></div>
      </form>
    </div>
  )
}

function JobDrawer({ job, log, onClose, onRefresh, onCancel, onRetry }: { job: Job; log: string; onClose: () => void; onRefresh: () => void; onCancel: () => void; onRetry: () => void }) {
  return (
    <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <aside className="job-drawer">
        <div className="drawer-header"><div><span className="section-kicker">Job {job.id.slice(0, 12)}</span><h2>{job.title}</h2></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div>
        <div className="job-summary"><StatusMark status={job.status} /><span><Clock3 size={14} /> {relativeTime(job.started_at || job.created_at)}</span><span><Terminal size={14} /> {job.tmux_session || 'session closed'}</span></div>
        {job.error && <div className="drawer-error"><CircleAlert size={17} /><span>{job.error}</span></div>}
        <section className="drawer-section"><div className="drawer-section-title"><h3>Acceptance evidence</h3><button className="icon-button" onClick={onRefresh}><RefreshCw size={16} /></button></div><div className="evidence-list">{(job.evidence || []).map((item) => <div className={item.passed ? 'passed' : 'failed'} key={item.id}>{item.passed ? <CheckCircle2 size={17} /> : <CircleAlert size={17} />}<span><strong>{item.label}</strong><small>{item.detail}</small></span></div>)}{!job.evidence?.length && <p className="drawer-empty">Evidence is evaluated when the command exits.</p>}</div></section>
        <section className="drawer-section log-section"><div className="drawer-section-title"><h3>Log</h3><span>{job.log_path}</span></div><pre>{log || 'Waiting for output…'}</pre></section>
        <div className="drawer-actions">
          {ACTIVE_STATUSES.has(job.status) && <button className="danger-button" onClick={onCancel}><Square size={16} /> Stop</button>}
          {['blocked', 'failed', 'interrupted', 'cancelled'].includes(job.status) && <button className="secondary-button" onClick={onRetry}><RotateCcw size={16} /> Retry</button>}
          <button className="secondary-button" onClick={onRefresh}><RefreshCw size={16} /> Refresh</button>
        </div>
      </aside>
    </div>
  )
}

export default App
