import type { TimelineCopy } from '../tasks/timeline'
import type { Language } from './uiPreferences'

export type WorkspaceCopy = {
  page: {
    eyebrow: string
    title: string
  }
  toolbar: {
    preferencesLabel: string
    language: string
    english: string
    chinese: string
    theme: string
    light: string
    dark: string
    modelRuntime: string
    localModel: string
    apiModel: string
    runtimeSwitching: string
    runtimeLoadError: string
    runtimeSwitchError: string
    localRuntimeStatusLabel: string
    localRuntimeStatuses: Record<'unknown' | 'stopped' | 'starting' | 'ready' | 'stopping' | 'error', string>
    localRuntimeErrorDetail: (message: string) => string
  }
  dataset: {
    kicker: string
    title: string
    refresh: string
    selectDataset: string
    noDatasets: string
    countsLabel: string
    tables: string
    ready: string
    inProgress: string
    failed: string
    showTools: string
    hideTools: string
    createTitle: string
    datasetName: string
    description: string
    create: string
    uploadTitle: string
    files: string
    folder: string
    dropZone: string
    selectedFiles: (count: number) => string
    uploadedBy: string
    tableNamePrefix: string
    upload: string
    uploading: string
    uploadSummary: string
    accepted: (count: number) => string
    rejected: (count: number) => string
    skipped: (count: number) => string
    recentTables: string
    noTables: string
    loadError: string
    mutationError: string
  }
  control: {
    kicker: string
    title: string
    ready: string
    contextLabel: string
    tenant: string
    tables: string
    tablesReady: (count: number) => string
    mode: string
    modes: Record<'discover' | 'integrate' | 'match', string>
    tenantOptions: Record<'default' | 'benchmark', string>
    executionProfile: string
    executionProfiles: Record<'reproducible' | 'fast' | 'joinTuned', string>
    advancedParameters: string
    showAdvancedParameters: string
    hideAdvancedParameters: string
    l1Threshold: string
    l2Threshold: string
    l3Threshold: string
    matcherThreshold: string
    matcherTopK: string
    resetDefaults: string
    queryTable: string
    sourceTable: string
    targetTable: string
    previewQueryTable: string
    previewSourceTable: string
    previewTargetTable: string
    run: string
    running: string
    cancel: string
  }
  results: {
    kicker: string
    title: string
    taskLabel: (taskId: string) => string
    summaryLabel: string
    placeholderLabel: string
    summaryMode: string
    summaryRuntime: (seconds: number | null) => string
    summaryCandidates: (count: number) => string
    summaryMappings: (count: number) => string
    summaryTenant: string
    viewsLabel: string
    tabs: Record<'graph' | 'ranking' | 'mappings' | 'raw', string>
    emptyTitle: string
    emptyDescription: string
    noLayerScores: string
    noRanking: string
    matchNoRanking: string
    rankingAria: string
    rankingTitle: string
    candidates: (count: number) => string
    candidateScore: (rank: number) => string
    mappingsAria: string
    mappingsTitle: string
    previewQueryTable: string
    previewTargetTable: string
    alignments: (count: number) => string
    matched: string
    rejected: string
    scenarioLabel: (scenario: string) => string
    errorDetails: string
    mappingConfidence: string
    noReasoning: string
    rawTitle: string
  }
  tablePreview: {
    title: string
    close: string
    loading: string
    loadError: string
    rows: (count: number | null | undefined) => string
    columns: (count: number | null | undefined) => string
    dataset: string
    status: string
    sampleRows: string
    noRows: string
    nullValue: string
  }
  trace: {
    kicker: string
    title: string
    eventCount: (count: number) => string
    pipelineLabel: string
    stepsLabel: (agentLabel: string) => string
    currentStep: string
    waiting: string
    stepsComplete: (done: number, total: number) => string
    candidates: (input: string, output: string) => string
    produced: (output: string) => string
    queued: (input: string) => string
    fallback: (fallback: string) => string
    elapsed: (seconds: number) => string
    eventsTitle: string
    eventsKicker: string
    defaultActor: string
    agents: TimelineCopy
  }
}

export const workspaceCopy: Record<Language, WorkspaceCopy> = {
  en: {
    page: {
      eyebrow: 'Adaptive scenario matching · Cascaded filtering',
      title: 'AdaCascade Workbench',
    },
    toolbar: {
      preferencesLabel: 'Workspace preferences',
      language: 'Language',
      english: 'English',
      chinese: '中文',
      theme: 'Theme',
      light: 'Light',
      dark: 'Dark',
      modelRuntime: 'Model runtime',
      localModel: 'Local model',
      apiModel: 'API model',
      runtimeSwitching: 'Switching…',
      runtimeLoadError: 'Runtime status is unavailable. Switching is disabled until it can be loaded.',
      runtimeSwitchError: 'Runtime switch failed. The previous backend is still selected.',
      localRuntimeStatusLabel: 'Local vLLM status',
      localRuntimeStatuses: {
        unknown: 'unknown',
        stopped: 'stopped',
        starting: 'starting',
        ready: 'ready',
        stopping: 'stopping',
        error: 'error',
      },
      localRuntimeErrorDetail: (message) => `Error: ${message}`,
    },
    dataset: {
      kicker: 'Dataset scope',
      title: 'Dataset Panel',
      refresh: 'Refresh',
      selectDataset: 'Dataset',
      noDatasets: 'No Datasets',
      countsLabel: 'Dataset table counts',
      tables: 'Tables',
      ready: 'Ready',
      inProgress: 'In progress',
      failed: 'Failed',
      showTools: 'Show Dataset tools',
      hideTools: 'Hide Dataset tools',
      createTitle: 'Create Dataset',
      datasetName: 'Dataset name',
      description: 'Description',
      create: 'Create Dataset',
      uploadTitle: 'Upload tables',
      files: 'Files',
      folder: 'Folder',
      dropZone: 'Drop files or folders',
      selectedFiles: (count) => `${count} selected`,
      uploadedBy: 'Uploaded by',
      tableNamePrefix: 'Table name prefix',
      upload: 'Upload to Dataset',
      uploading: 'Uploading…',
      uploadSummary: 'Upload summary',
      accepted: (count) => `${count} accepted`,
      rejected: (count) => `${count} rejected`,
      skipped: (count) => `${count} skipped`,
      recentTables: 'Recent tables',
      noTables: 'No ready tables in this Dataset yet.',
      loadError: 'Datasets could not be loaded.',
      mutationError: 'Dataset operation failed.',
    },
    control: {
      kicker: 'Launch vector',
      title: 'Task Control',
      ready: 'Ready',
      contextLabel: 'Workspace context',
      tenant: 'Tenant',
      tables: 'Tables',
      tablesReady: (count) => `${count} ready`,
      mode: 'Mode',
      modes: { discover: 'Discover', integrate: 'Integrate', match: 'Match' },
      tenantOptions: { default: 'default (demo)', benchmark: 'benchmark (full)' },
      executionProfile: 'Execution profile',
      executionProfiles: { reproducible: 'Reproducible', fast: 'Demo fast', joinTuned: 'JOIN tuned recall' },
      advancedParameters: 'Advanced parameters',
      showAdvancedParameters: 'Show advanced parameters',
      hideAdvancedParameters: 'Hide advanced parameters',
      l1Threshold: 'L1 threshold',
      l2Threshold: 'L2 threshold',
      l3Threshold: 'L3 LLM threshold',
      matcherThreshold: 'Matcher threshold',
      matcherTopK: 'Matcher top-k',
      resetDefaults: 'Reset to defaults',
      queryTable: 'Query table',
      sourceTable: 'Source table',
      targetTable: 'Target table',
      previewQueryTable: 'Preview query table',
      previewSourceTable: 'Preview source table',
      previewTargetTable: 'Preview target table',
      run: 'Run AdaCascade',
      running: 'Running AdaCascade…',
      cancel: 'Cancel task',
    },
    results: {
      kicker: 'Central workspace',
      title: 'Result Workspace',
      taskLabel: (taskId) => `Task ${taskId}`,
      summaryLabel: 'Result summary',
      placeholderLabel: 'Result dashboard placeholder',
      summaryMode: 'Mode',
      summaryRuntime: (seconds) => (seconds === null ? 'Runtime pending' : `${seconds}s runtime`),
      summaryCandidates: (count) => `${count} ${count === 1 ? 'candidate' : 'candidates'}`,
      summaryMappings: (count) => `${count} ${count === 1 ? 'mapping' : 'mappings'}`,
      summaryTenant: 'Tenant',
      viewsLabel: 'Result views',
      tabs: { graph: 'Graph', ranking: 'Ranking', mappings: 'Mappings', raw: 'Raw JSON' },
      emptyTitle: 'No active task',
      emptyDescription:
        'Choose a mode and table context, then run AdaCascade to populate graph, ranking, mappings, and raw JSON views. This preview intentionally does not auto-run.',
      noLayerScores: 'No layer scores',
      noRanking: 'No discovery ranking was produced for this task.',
      matchNoRanking: 'Match mode compares the selected source and target tables directly, so no discovery ranking is produced.',
      rankingAria: 'Ranking results',
      rankingTitle: 'Ranking',
      candidates: (count) => `${count} candidates`,
      candidateScore: (rank) => `Candidate ${rank} score`,
      mappingsAria: 'Column mapping results',
      mappingsTitle: 'Mappings',
      previewQueryTable: 'Preview query table',
      previewTargetTable: 'Preview target table',
      alignments: (count) => `${count} alignments`,
      matched: 'Matched',
      rejected: 'Rejected',
      scenarioLabel: (scenario) => `Scenario ${scenario}`,
      errorDetails: 'Error details',
      mappingConfidence: 'Mapping confidence',
      noReasoning: 'No reasoning supplied.',
      rawTitle: 'Raw JSON',
    },
    tablePreview: {
      title: 'Table preview',
      close: 'Close preview',
      loading: 'Loading table preview…',
      loadError: 'Unable to load table preview.',
      rows: (count) => `${count ?? '—'} rows`,
      columns: (count) => `${count ?? '—'} columns`,
      dataset: 'Dataset',
      status: 'Status',
      sampleRows: 'Sample rows',
      noRows: 'No sample rows available.',
      nullValue: '—',
    },
    trace: {
      kicker: 'Agent pipeline',
      title: 'Four-agent execution',
      eventCount: (count) => `${count} events`,
      pipelineLabel: 'AdaCascade agent pipeline',
      stepsLabel: (agentLabel) => `${agentLabel} steps`,
      currentStep: 'Current step',
      waiting: 'Waiting for task events',
      stepsComplete: (done, total) => `${done}/${total} steps complete`,
      candidates: (input, output) => `${input} → ${output} candidates`,
      produced: (output) => `${output} produced`,
      queued: (input) => `${input} queued`,
      fallback: (fallback) => `Fallback: ${fallback}`,
      elapsed: (seconds) => `${seconds}s elapsed`,
      eventsTitle: 'Recent events',
      eventsKicker: 'supporting log',
      defaultActor: 'Task',
      agents: {
        Planner: {
          label: 'Planner',
          purpose: 'Builds the task plan and mode routing.',
          steps: {
            overview: { label: 'Plan routing', summary: 'Chooses discover, match, or integrate execution path.' },
          },
        },
        Profiling: {
          label: 'Profiling',
          purpose: 'Extracts table and column metadata.',
          steps: {
            overview: { label: 'Table profiling', summary: 'Reads table shape, columns, types, and value statistics.' },
          },
        },
        Retrieval: {
          label: 'Retrieval',
          purpose: 'Narrows the lake with TLCF cascade.',
          steps: {
            L1: { label: 'Lexical filter', summary: 'Uses table text and schema keywords to keep plausible candidates.' },
            L2: { label: 'Vector recall', summary: 'Queries embeddings to recover semantically similar tables.' },
            L3: { label: 'LLM rerank', summary: 'Asks the LLM to rerank the strongest candidates.' },
          },
        },
        Matcher: {
          label: 'Matcher',
          purpose: 'Verifies column alignments and final mappings.',
          steps: {
            filtering: { label: 'Candidate filter', summary: 'Keeps likely column pairs before expensive verification.' },
            LLM: { label: 'LLM verification', summary: 'Checks semantic equivalence for candidate column pairs.' },
            decision: { label: 'One-to-one decision', summary: 'Selects final non-conflicting column mappings.' },
          },
        },
      },
    },
  },
  zh: {
    page: {
      eyebrow: '自适应场景匹配 · 级联过滤',
      title: 'AdaCascade 工作台',
    },
    toolbar: {
      preferencesLabel: '工作区偏好',
      language: '语言',
      english: 'English',
      chinese: '中文',
      theme: '主题',
      light: '浅色',
      dark: '深色',
      modelRuntime: '模型运行时',
      localModel: '本地模型',
      apiModel: 'API 模型',
      runtimeSwitching: '切换中…',
      runtimeLoadError: '运行时状态不可用。加载成功前无法切换。',
      runtimeSwitchError: '运行时切换失败，仍保留之前的后端。',
      localRuntimeStatusLabel: '本地 vLLM 状态',
      localRuntimeStatuses: {
        unknown: '未知',
        stopped: '未启动',
        starting: '启动中',
        ready: '已启动',
        stopping: '停止中',
        error: '启动失败',
      },
      localRuntimeErrorDetail: (message) => `启动失败：${message}`,
    },
    dataset: {
      kicker: '数据集范围',
      title: '数据集面板',
      refresh: '刷新',
      selectDataset: '数据集',
      noDatasets: '暂无数据集',
      countsLabel: '数据集表统计',
      tables: '表',
      ready: '就绪',
      inProgress: '处理中',
      failed: '失败',
      showTools: '展开数据集工具',
      hideTools: '收起数据集工具',
      createTitle: '新建数据集',
      datasetName: '数据集名称',
      description: '描述',
      create: '新建数据集',
      uploadTitle: '上传表',
      files: '文件',
      folder: '文件夹',
      dropZone: '拖放文件或文件夹',
      selectedFiles: (count) => `已选择 ${count} 个`,
      uploadedBy: '上传者',
      tableNamePrefix: '表名前缀',
      upload: '上传到数据集',
      uploading: '上传中…',
      uploadSummary: '上传摘要',
      accepted: (count) => `${count} 个接受`,
      rejected: (count) => `${count} 个拒绝`,
      skipped: (count) => `${count} 个跳过`,
      recentTables: '最近表状态',
      noTables: '此数据集暂无就绪表。',
      loadError: '数据集加载失败。',
      mutationError: '数据集操作失败。',
    },
    control: {
      kicker: '启动入口',
      title: '任务控制',
      ready: '就绪',
      contextLabel: '工作区上下文',
      tenant: '租户',
      tables: '表',
      tablesReady: (count) => `${count} 张就绪`,
      mode: '模式',
      modes: { discover: '表发现', integrate: '数据集成', match: '模式匹配' },
      tenantOptions: { default: 'default（演示）', benchmark: 'benchmark（基准）' },
      executionProfile: '执行配置',
      executionProfiles: { reproducible: '可复现', fast: '演示加速', joinTuned: 'JOIN 召回优化' },
      advancedParameters: '高级参数',
      showAdvancedParameters: '展开高级参数',
      hideAdvancedParameters: '收起高级参数',
      l1Threshold: 'L1 阈值',
      l2Threshold: 'L2 阈值',
      l3Threshold: 'L3 LLM 判定阈值',
      matcherThreshold: '匹配判定阈值',
      matcherTopK: '匹配候选 top-k',
      resetDefaults: '重置为默认值',
      queryTable: '查询表',
      sourceTable: '源表',
      targetTable: '目标表',
      previewQueryTable: '预览查询表',
      previewSourceTable: '预览源表',
      previewTargetTable: '预览目标表',
      run: '运行 AdaCascade',
      running: 'AdaCascade 运行中…',
      cancel: '取消任务',
    },
    results: {
      kicker: '中央工作区',
      title: '结果工作区',
      taskLabel: (taskId) => `任务 ${taskId}`,
      summaryLabel: '结果摘要',
      placeholderLabel: '结果仪表盘占位区',
      summaryMode: '模式',
      summaryRuntime: (seconds) => (seconds === null ? '耗时待定' : `耗时 ${seconds} 秒`),
      summaryCandidates: (count) => `${count} 个候选`,
      summaryMappings: (count) => `${count} 个映射`,
      summaryTenant: '租户',
      viewsLabel: '结果视图',
      tabs: { graph: '流程图', ranking: '候选排序', mappings: '列映射', raw: '原始 JSON' },
      emptyTitle: '暂无活跃任务',
      emptyDescription: '选择模式和表上下文后运行 AdaCascade，即可查看流程图、候选排序、列映射和原始 JSON。此预览不会自动运行。',
      noLayerScores: '暂无层级分数',
      noRanking: '此任务未产生表发现候选排序。',
      matchNoRanking: '模式匹配会直接比较所选源表和目标表，因此不会产生表发现候选排序。',
      rankingAria: '候选排序结果',
      rankingTitle: '候选排序',
      candidates: (count) => `${count} 个候选`,
      candidateScore: (rank) => `候选 ${rank} 分数`,
      mappingsAria: '列映射结果',
      mappingsTitle: '映射',
      previewQueryTable: '预览查询表',
      previewTargetTable: '预览目标表',
      alignments: (count) => `${count} 个对齐`,
      matched: '已匹配',
      rejected: '已拒绝',
      scenarioLabel: (scenario) => `场景 ${scenario}`,
      errorDetails: '错误详情',
      mappingConfidence: '映射置信度',
      noReasoning: '未提供理由。',
      rawTitle: '原始 JSON',
    },
    tablePreview: {
      title: '表格预览',
      close: '关闭预览',
      loading: '正在加载表格预览…',
      loadError: '无法加载表格预览。',
      rows: (count) => `${count ?? '—'} 行`,
      columns: (count) => `${count ?? '—'} 列`,
      dataset: '数据集',
      status: '状态',
      sampleRows: '样例数据',
      noRows: '暂无样例数据。',
      nullValue: '—',
    },
    trace: {
      kicker: '智能体流水线',
      title: '四智能体执行',
      eventCount: (count) => `${count} 条事件`,
      pipelineLabel: 'AdaCascade 智能体流水线',
      stepsLabel: (agentLabel) => `${agentLabel}步骤`,
      currentStep: '当前步骤',
      waiting: '等待任务事件',
      stepsComplete: (done, total) => `${done}/${total} 步完成`,
      candidates: (input, output) => `${input} → ${output} 个候选`,
      produced: (output) => `产出 ${output}`,
      queued: (input) => `${input} 个排队`,
      fallback: (fallback) => `降级：${fallback}`,
      elapsed: (seconds) => `已耗时 ${seconds} 秒`,
      eventsTitle: '最近事件',
      eventsKicker: '辅助日志',
      defaultActor: '任务',
      agents: {
        Planner: {
          label: '规划智能体',
          purpose: '生成任务计划并选择执行模式路由。',
          steps: {
            overview: { label: '模式路由', summary: '选择表发现、模式匹配或数据集成执行路径。' },
          },
        },
        Profiling: {
          label: '特征分析智能体',
          purpose: '抽取表级与列级特征。',
          steps: {
            overview: { label: '表特征分析', summary: '读取表规模、列模式、数据类型、缺失率、基数特征和值分布统计。' },
          },
        },
        Retrieval: {
          label: '检索智能体',
          purpose: '通过三层级联过滤（TLCF）缩小数据湖候选表范围。',
          steps: {
            L1: { label: '词法过滤', summary: '基于表文本、列名和模式关键词保留候选表。' },
            L2: { label: '向量召回', summary: '基于表嵌入召回语义相似候选表。' },
            L3: { label: 'LLM 复核', summary: '使用 LLM 对高置信候选表进行语义复核与重排。' },
          },
        },
        Matcher: {
          label: '匹配智能体',
          purpose: '执行列级匹配验证并生成最终列映射。',
          steps: {
            filtering: { label: '列候选过滤', summary: '在 LLM 验证前保留高相似度候选列对。' },
            LLM: { label: 'LLM 验证', summary: '判定候选列对是否语义等价。' },
            decision: { label: '一对一决策', summary: '选择最终无冲突的一对一列映射。' },
          },
        },
      },
    },
  },
}

export function getWorkspaceCopy(language: Language = 'en'): WorkspaceCopy {
  return workspaceCopy[language]
}
