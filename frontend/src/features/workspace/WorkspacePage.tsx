import { useCallback, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createDataset, listDatasets, uploadDatasetTables } from '../../api/datasets'
import type { UploadDatasetTablesResponse } from '../../api/datasets'
import { subscribeTaskEvents } from '../../api/events'
import { getLlmRuntime, updateLlmRuntime } from '../../api/runtime'
import { listTables } from '../../api/tables'
import { cancelTask, getTask, startDiscover, startIntegrate, startMatch } from '../../api/tasks'
import { useTaskStore } from '../tasks/taskStore'
import type { TaskMode } from '../tasks/taskTypes'

const defaultTenantId = import.meta.env.VITE_DEFAULT_TENANT_ID ?? 'default'
const tenantOptions = ['default', 'benchmark'] as const
import { AgentTracePanel } from './AgentTracePanel'
import { DatasetPanel } from './DatasetPanel'
import { getWorkspaceCopy } from './i18n'
import { ResultWorkspace } from './ResultWorkspace'
import { TaskControlPanel, type TenantOption } from './TaskControlPanel'
import { PAPER_PARAMETER_DEFAULTS, type AdvancedParameters, type ExecutionProfile } from './parameters'
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

  const [tenantId, setTenantId] = useState(() => getSearchParam(params, 'tenant_id', defaultTenantId))
  const [selectedDatasetId, setSelectedDatasetId] = useState(() => getSearchParam(params, 'dataset_id', ''))
  const [uploadSummary, setUploadSummary] = useState<UploadDatasetTablesResponse | null>(null)
  const [datasetMutationError, setDatasetMutationError] = useState<string | null>(null)
  const [executionProfile, setExecutionProfile] = useState<ExecutionProfile>('reproducible')
  const [parameters, setParameters] = useState<AdvancedParameters>(PAPER_PARAMETER_DEFAULTS)
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
  const tenantSelectOptions = useMemo<TenantOption[]>(
    () => tenantOptions.map((value) => ({ value, label: copy.control.tenantOptions[value] })),
    [copy.control.tenantOptions],
  )
  const taskOptions = useMemo(
    () => ({
      ...parameters,
      ...(executionProfile === 'fast'
        ? {
            llm_cache_enabled: true,
            llm_batch_size: 10,
            llm_concurrency: 24,
            matcher_llm_concurrency: 8,
          }
        : {}),
      ...(executionProfile === 'joinTuned'
        ? {
            column_recall_enabled: true,
            column_recall_top_k: 10,
            column_recall_add_k: 10,
            matcher_llm_concurrency: 8,
          }
        : {}),
    }),
    [executionProfile, parameters],
  )

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

  const datasetsQuery = useQuery({
    queryKey: ['datasets', tenantId],
    queryFn: () => listDatasets(tenantId),
  })
  const datasets = useMemo(() => datasetsQuery.data?.items ?? [], [datasetsQuery.data?.items])

  useEffect(() => {
    if (selectedDatasetId || datasets.length === 0) return
    setSelectedDatasetId(datasets[0]?.dataset_id ?? '')
  }, [datasets, selectedDatasetId])

  const tablesQuery = useQuery({
    queryKey: ['tables', tenantId, selectedDatasetId],
    queryFn: () => listTables(tenantId, selectedDatasetId || undefined),
    enabled: Boolean(selectedDatasetId),
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

  const createDatasetMutation = useMutation({
    mutationFn: (payload: { dataset_name: string; description?: string }) => createDataset(tenantId, payload),
    onSuccess: (dataset) => {
      setDatasetMutationError(null)
      void queryClient.invalidateQueries({ queryKey: ['datasets', tenantId] })
      setSelectedDatasetId(dataset.dataset_id)
    },
    onError: () => {
      setDatasetMutationError(copy.dataset.mutationError)
    },
  })

  const uploadDatasetMutation = useMutation({
    mutationFn: ({ files, options }: { files: File[]; options: { uploadedBy?: string; tableNamePrefix?: string } }) =>
      uploadDatasetTables(tenantId, selectedDatasetId, files, options),
    onSuccess: (summary) => {
      setDatasetMutationError(null)
      setUploadSummary(summary)
      void queryClient.invalidateQueries({ queryKey: ['datasets', tenantId] })
      void queryClient.invalidateQueries({ queryKey: ['tables', tenantId, selectedDatasetId] })
    },
    onError: () => {
      setDatasetMutationError(copy.dataset.mutationError)
    },
  })

  const startTaskMutation = useMutation({
    mutationFn: () => {
      if (mode === 'discover') return startDiscover(tenantId, queryTableId, taskOptions, selectedDatasetId || undefined)
      if (mode === 'match') return startMatch(tenantId, sourceTableId, targetTableId, taskOptions, selectedDatasetId || undefined)
      return startIntegrate(tenantId, queryTableId, taskOptions, selectedDatasetId || undefined)
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

  const cancelTaskMutation = useMutation({
    mutationFn: () => cancelTask(tenantId, currentTaskId ?? ''),
    onSuccess: (task) => {
      queryClient.setQueryData(['task', tenantId, task.task_id], task)
      setStreamError(null)
    },
    onError: (error) => {
      setStreamError(errorMessage(error))
    },
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
    Boolean(selectedDatasetId) &&
    tables.length > 0 &&
    !isRunning &&
    (mode === 'match' ? Boolean(sourceTableId && targetTableId) : Boolean(queryTableId))
  const handleRun = useCallback(() => {
    if (!canRun) return
    startTaskMutation.mutate()
  }, [canRun, startTaskMutation])

  const handleCancel = useCallback(() => {
    if (!currentTaskId || cancelTaskMutation.isPending) return
    cancelTaskMutation.mutate()
  }, [cancelTaskMutation, currentTaskId])

  const resetTaskContext = useCallback(() => {
    setQueryTableId('')
    setSourceTableId('')
    setTargetTableId('')
    setStreamError(null)
    setCurrentTaskId(null)
    resetLiveState()
  }, [resetLiveState, setCurrentTaskId])

  const handleTenantChange = useCallback(
    (nextTenantId: string) => {
      setTenantId(nextTenantId)
      setSelectedDatasetId('')
      setUploadSummary(null)
      setDatasetMutationError(null)
      resetTaskContext()
    },
    [resetTaskContext],
  )

  const handleDatasetChange = useCallback(
    (nextDatasetId: string) => {
      setSelectedDatasetId(nextDatasetId)
      setUploadSummary(null)
      setDatasetMutationError(null)
      resetTaskContext()
    },
    [resetTaskContext],
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme

    return () => {
      delete document.documentElement.dataset.theme
    }
  }, [theme])

  const handleLanguageChange = useCallback((nextLanguage: Language) => {
    setLanguage(nextLanguage)
    writeLanguage(nextLanguage)
  }, [])

  const handleThemeChange = useCallback((nextTheme: ThemeMode) => {
    setTheme(nextTheme)
    writeTheme(nextTheme)
  }, [])

  const handleParameterChange = useCallback((key: keyof AdvancedParameters, value: number) => {
    if (Number.isNaN(value)) return
    setParameters((current) => ({ ...current, [key]: value }))
  }, [])

  const handleResetParameters = useCallback(() => {
    setParameters(PAPER_PARAMETER_DEFAULTS)
  }, [])

  const handleRuntimeBackendChange = useCallback(
    (backend: RuntimeBackend) => {
      if (runtimeBackend === null || isRunning || runtimeMutation.isPending || backend === runtimeBackend) return
      runtimeMutation.mutate(backend)
    },
    [isRunning, runtimeBackend, runtimeMutation],
  )

  const handleRefreshDatasets = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['datasets', tenantId] })
    void queryClient.invalidateQueries({ queryKey: ['tables', tenantId, selectedDatasetId] })
  }, [queryClient, selectedDatasetId, tenantId])

  useEffect(() => {
    const hasInProgressTables = tables.some((table) => table.status === 'INGESTED' || table.status === 'PROFILING')
    if (!hasInProgressTables || !selectedDatasetId) return undefined
    const interval = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ['datasets', tenantId] })
      void queryClient.invalidateQueries({ queryKey: ['tables', tenantId, selectedDatasetId] })
    }, 2000)
    return () => window.clearInterval(interval)
  }, [queryClient, selectedDatasetId, tables, tenantId])

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
        <div className="workspace-sidebar">
          <DatasetPanel
            datasets={datasets}
            selectedDatasetId={selectedDatasetId}
            tables={tables}
            isLoading={datasetsQuery.isLoading || tablesQuery.isLoading}
            isMutating={createDatasetMutation.isPending || uploadDatasetMutation.isPending}
            uploadSummary={uploadSummary}
            error={datasetsQuery.isError ? copy.dataset.loadError : datasetMutationError}
            onDatasetChange={handleDatasetChange}
            onCreateDataset={(payload) => createDatasetMutation.mutate(payload)}
            onUploadTables={(files, options) => uploadDatasetMutation.mutate({ files, options })}
            onRefresh={handleRefreshDatasets}
            language={language}
          />
          <TaskControlPanel
            tenantId={tenantId}
          tenantOptions={tenantSelectOptions}
          executionProfile={executionProfile}
          parameters={parameters}
          mode={mode}
          tables={tables}
          queryTableId={queryTableId}
          sourceTableId={sourceTableId}
          targetTableId={targetTableId}
          isRunning={isRunning}
          onTenantChange={handleTenantChange}
          onExecutionProfileChange={setExecutionProfile}
          onParameterChange={handleParameterChange}
          onResetParameters={handleResetParameters}
          onModeChange={setMode}
          onQueryTableChange={setQueryTableId}
          onSourceTableChange={setSourceTableId}
          onTargetTableChange={setTargetTableId}
          onRun={handleRun}
            onCancel={handleCancel}
            language={language}
          />
        </div>
        <ResultWorkspace task={taskQuery.data ?? null} tables={tables} language={language} />
        <AgentTracePanel timeline={timeline} events={events} streamError={streamError} language={language} />
      </div>
    </div>
  )
}
