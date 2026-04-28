import { useCallback, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { subscribeTaskEvents } from '../../api/events'
import { listTables } from '../../api/tables'
import { getTask, startDiscover, startIntegrate, startMatch } from '../../api/tasks'
import { useTaskStore } from '../tasks/taskStore'
import type { TaskMode } from '../tasks/taskTypes'
import { AgentTracePanel } from './AgentTracePanel'
import { ResultWorkspace } from './ResultWorkspace'
import { TaskControlPanel } from './TaskControlPanel'

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
  const tenantId = getSearchParam(params, 'tenant_id', 'demo-lab')

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

  return (
    <div className="workspace-shell">
      <header className="workspace-topbar">
        <div>
          <p className="eyebrow">Adaptive scenario matching · Cascaded filtering</p>
          <h1>AdaCascade Workbench</h1>
        </div>
        <aside className="demo-warning" aria-label="Local demo security warning">
          Local demo environment. Do not expose this build or its browser-visible API key on a public network.
        </aside>
      </header>

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
        />
        <ResultWorkspace task={taskQuery.data ?? null} />
        <AgentTracePanel timeline={timeline} events={events} streamError={streamError} />
      </div>
    </div>
  )
}
