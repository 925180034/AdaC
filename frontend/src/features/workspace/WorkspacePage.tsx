import { useCallback, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { subscribeTaskEvents } from '../../api/events'
import { getLlmRuntime, updateLlmRuntime } from '../../api/runtime'
import { listTables } from '../../api/tables'
import { getTask, startDiscover, startIntegrate, startMatch } from '../../api/tasks'
import { useTaskStore } from '../tasks/taskStore'
import type { TaskMode } from '../tasks/taskTypes'

const defaultTenantId = import.meta.env.VITE_DEFAULT_TENANT_ID ?? 'default'
import { AgentTracePanel } from './AgentTracePanel'
import { getWorkspaceCopy } from './i18n'
import { ResultWorkspace } from './ResultWorkspace'
import { TaskControlPanel } from './TaskControlPanel'
import { WorkspaceToolbar } from './WorkspaceToolbar'
import { readLanguage, readTheme, writeLanguage, writeTheme } from './uiPreferences'
import type { Language, ThemeMode } from './uiPreferences'
import type { RuntimeBackend } from '../../api/runtime'

function getSearchParam(params: URLSearchParams, key: string, fallback: string): string {
  return params.get(key) || fallback
}

function getInitialMode(params: URLSearchParams): TaskMode {
  const mode = params.get('mode')
  if (mode === 'discover' || mode === 'integrate' || mode === 'match') return mode
  return 'integrate'
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === 'AbortError'
    : error instanceof Error && error.name === 'AbortError'
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Task event stream failed unexpectedly'
}

export function WorkspacePage() {
  const [params] = useState(() => new URLSearchParams(window.location.search))
  const queryClient = useQueryClient()
  const currentTaskId = useTaskStore((state) => state.currentTaskId)
  const events = useTaskStore((state) => state.events)
  const timeline = useTaskStore((state) => state.timeline)
  const setCurrentTaskId = useTaskStore((state) => state.setCurrentTaskId)
  const appendEvent = useTaskStore((state) => state.appendEvent)
  const resetLiveState = useTaskStore((state) => state.resetLiveState)

  const [mode, setMode] = useState<TaskMode>(() => getInitialMode(params))
  const [queryTableId, setQueryTableId] = useState(() => getSearchParam(params, 'query_table_id', ''))
  const [sourceTableId, setSourceTableId] = useState(() => getSearchParam(params, 'source_table_id', ''))
  const [targetTableId, setTargetTableId] = useState(() => getSearchParam(params, 'target_table_id', ''))
  const [streamError, setStreamError] = useState<string | null>(null)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [pendingRuntimeBackend, setPendingRuntimeBackend] = useState<RuntimeBackend | null>(null)
  const [language, setLanguage] = useState(readLanguage)
  const [theme, setTheme] = useState(readTheme)
  const copy = getWorkspaceCopy(language)
  const tenantId = getSearchParam(params, 'tenant_id', defaultTenantId)

  const runtimeQuery = useQuery({
    queryKey: ['llm-runtime', tenantId],
    queryFn: () => getLlmRuntime(tenantId),
  })

  const runtimeMutation = useMutation({
    mutationFn: (backend: RuntimeBackend) => updateLlmRuntime(tenantId, backend),
    onMutate: (backend) => {
      setRuntimeError(null)
      setPendingRuntimeBackend(backend)
    },
    onSuccess: (runtime) => {
      queryClient.setQueryData(['llm-runtime', tenantId], runtime)
    },
    onError: () => {
      setRuntimeError(copy.toolbar.runtimeSwitchError)
    },
    onSettled: () => {
      setPendingRuntimeBackend(null)
    },
  })
  const runtimeBackend = runtimeQuery.data?.backend ?? null
  const runtimeQueryError = runtimeQuery.isError ? copy.toolbar.runtimeLoadError : null

  const tablesQuery = useQuery({
    queryKey: ['tables', tenantId],
    queryFn: () => listTables(tenantId),
  })
  const tables = useMemo(() => tablesQuery.data?.items ?? [], [tablesQuery.data?.items])

  useEffect(() => {
    if (tables.length === 0) return
    const firstTableId = tables[0]?.table_id ?? ''
    const secondTableId = tables[1]?.table_id ?? firstTableId

    if (!queryTableId) setQueryTableId(firstTableId)
    if (!sourceTableId) setSourceTableId(firstTableId)
    if (!targetTableId) setTargetTableId(secondTableId)
  }, [queryTableId, sourceTableId, tables, targetTableId])

  const startTaskMutation = useMutation({
    mutationFn: () => {
      if (mode === 'discover') return startDiscover(tenantId, queryTableId)
      if (mode === 'match') return startMatch(tenantId, sourceTableId, targetTableId)
      return startIntegrate(tenantId, queryTableId)
    },
    onSuccess: (task) => {
      resetLiveState()
      setStreamError(null)
      setCurrentTaskId(task.task_id)
    },
  })

  const taskQuery = useQuery({
    queryKey: ['task', tenantId, currentTaskId],
    queryFn: () => getTask(tenantId, currentTaskId ?? ''),
    enabled: Boolean(currentTaskId),
  })

  useEffect(() => {
    if (!currentTaskId) return undefined

    const controller = new AbortController()
    setStreamError(null)
    void subscribeTaskEvents(
      tenantId,
      currentTaskId,
      (event) => {
        if (event.task_id !== currentTaskId) {
          return
        }

        appendEvent(event)
        if (event.type === 'task_completed') {
          void queryClient.invalidateQueries({ queryKey: ['task', tenantId, currentTaskId] })
          controller.abort()
        }
      },
      controller.signal,
    ).catch((error: unknown) => {
      if (isAbortError(error) || controller.signal.aborted) {
        return
      }

      setStreamError(errorMessage(error))
    })

    return () => controller.abort()
  }, [appendEvent, currentTaskId, queryClient, tenantId])

  const isTerminalTask =
    taskQuery.data?.status === 'SUCCESS' ||
    taskQuery.data?.status === 'FAILED' ||
    taskQuery.data?.status === 'DEGRADED'
  const isRunning = startTaskMutation.isPending || (Boolean(currentTaskId) && !isTerminalTask)
  const canRun =
    tables.length > 0 &&
    !isRunning &&
    (mode === 'match' ? Boolean(sourceTableId && targetTableId) : Boolean(queryTableId))
  const handleRun = useCallback(() => {
    if (!canRun) return
    startTaskMutation.mutate()
  }, [canRun, startTaskMutation])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const handleLanguageChange = useCallback((nextLanguage: Language) => {
    setLanguage(nextLanguage)
    writeLanguage(nextLanguage)
  }, [])

  const handleThemeChange = useCallback((nextTheme: ThemeMode) => {
    setTheme(nextTheme)
    writeTheme(nextTheme)
  }, [])

  const handleRuntimeBackendChange = useCallback(
    (backend: RuntimeBackend) => {
      if (runtimeBackend === null || isRunning || runtimeMutation.isPending || backend === runtimeBackend) return
      runtimeMutation.mutate(backend)
    },
    [isRunning, runtimeBackend, runtimeMutation],
  )

  return (
    <div className="workspace-shell">
      <header className="workspace-topbar">
        <div>
          <p className="eyebrow">{copy.page.eyebrow}</p>
          <h1>{copy.page.title}</h1>
        </div>
        <aside className="demo-warning" aria-label={copy.page.warningLabel}>
          {copy.page.warning}
        </aside>
      </header>

      <WorkspaceToolbar
        copy={copy.toolbar}
        language={language}
        theme={theme}
        runtimeBackend={runtimeBackend}
        isRuntimePending={runtimeMutation.isPending}
        pendingRuntimeBackend={pendingRuntimeBackend}
        isRunning={isRunning}
        isRuntimeDisabled={runtimeBackend === null}
        onLanguageChange={handleLanguageChange}
        onThemeChange={handleThemeChange}
        onRuntimeBackendChange={handleRuntimeBackendChange}
      />

      {(runtimeQueryError || runtimeError) && (
        <p className="workspace-status workspace-status--error" role="alert">
          {runtimeQueryError ?? runtimeError}
        </p>
      )}

      <div className="workspace-grid">
        <TaskControlPanel
          tenantId={tenantId}
          mode={mode}
          tables={tables}
          queryTableId={queryTableId}
          sourceTableId={sourceTableId}
          targetTableId={targetTableId}
          isRunning={isRunning}
          onModeChange={setMode}
          onQueryTableChange={setQueryTableId}
          onSourceTableChange={setSourceTableId}
          onTargetTableChange={setTargetTableId}
          onRun={handleRun}
          language={language}
        />
        <ResultWorkspace task={taskQuery.data ?? null} language={language} />
        <AgentTracePanel timeline={timeline} events={events} streamError={streamError} language={language} />
      </div>
    </div>
  )
}
