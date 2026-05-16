import type { TimelineCopy } from '../tasks/timeline'
import type { Language } from './uiPreferences'

export type WorkspaceCopy = {
  page: {
    eyebrow: string
    title: string
    warningLabel: string
    warning: string
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
    l1Threshold: string
    l2Threshold: string
    l3Threshold: string
    matcherThreshold: string
    matcherTopK: string
    resetDefaults: string
    queryTable: string
    sourceTable: string
    targetTable: string
    run: string
    running: string
    cancel: string
    note: string
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
    alignments: (count: number) => string
    matched: string
    rejected: string
    scenarioLabel: (scenario: string) => string
    errorDetails: string
    mappingConfidence: string
    noReasoning: string
    rawTitle: string
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
      warningLabel: 'Local demo security warning',
      warning: 'Local demo environment. Do not expose this build or its browser-visible API key on a public network.',
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
      l1Threshold: 'L1 threshold',
      l2Threshold: 'L2 threshold',
      l3Threshold: 'L3 LLM threshold',
      matcherThreshold: 'Matcher threshold',
      matcherTopK: 'Matcher top-k',
      resetDefaults: 'Reset to paper defaults',
      queryTable: 'Query table',
      sourceTable: 'Source table',
      targetTable: 'Target table',
      run: 'Run AdaCascade',
      running: 'Running AdaCascade…',
      cancel: 'Cancel task',
      note: 'Static shell preview. REST submission and SSE reconciliation will attach in the next task.',
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
      alignments: (count) => `${count} alignments`,
      matched: 'Matched',
      rejected: 'Rejected',
      scenarioLabel: (scenario) => `Scenario ${scenario}`,
      errorDetails: 'Error details',
      mappingConfidence: 'Mapping confidence',
      noReasoning: 'No reasoning supplied.',
      rawTitle: 'Raw JSON',
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
      warningLabel: '本地演示安全提醒',
      warning: '本地演示环境。请勿将此构建或浏览器可见的 API Key 暴露到公网。',
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
      modes: { discover: '发现', integrate: '集成', match: '匹配' },
      tenantOptions: { default: 'default（演示）', benchmark: 'benchmark（全量）' },
      executionProfile: '执行配置',
      executionProfiles: { reproducible: '可复现', fast: '演示加速', joinTuned: 'JOIN 调优召回' },
      advancedParameters: '高级参数',
      l1Threshold: 'L1 阈值',
      l2Threshold: 'L2 阈值',
      l3Threshold: 'L3 LLM 阈值',
      matcherThreshold: 'Matcher 阈值',
      matcherTopK: 'Matcher top-k',
      resetDefaults: '重置为论文默认值',
      queryTable: '查询表',
      sourceTable: '源表',
      targetTable: '目标表',
      run: '运行 AdaCascade',
      running: 'AdaCascade 运行中…',
      cancel: '取消任务',
      note: '静态外壳预览。REST 提交与 SSE 对账将在后续任务接入。',
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
      tabs: { graph: '图谱', ranking: '排序', mappings: '映射', raw: '原始 JSON' },
      emptyTitle: '暂无活跃任务',
      emptyDescription: '选择模式和表上下文后运行 AdaCascade，即可查看图谱、排序、映射和原始 JSON。此预览不会自动运行。',
      noLayerScores: '暂无层级分数',
      noRanking: '此任务未产生发现排序结果。',
      matchNoRanking: '匹配模式会直接比较所选源表和目标表，因此不会产生发现排序。',
      rankingAria: '排序结果',
      rankingTitle: '排序',
      candidates: (count) => `${count} 个候选`,
      candidateScore: (rank) => `候选 ${rank} 分数`,
      mappingsAria: '列映射结果',
      mappingsTitle: '映射',
      alignments: (count) => `${count} 个对齐`,
      matched: '已匹配',
      rejected: '已拒绝',
      scenarioLabel: (scenario) => `场景 ${scenario}`,
      errorDetails: '错误详情',
      mappingConfidence: '映射置信度',
      noReasoning: '未提供理由。',
      rawTitle: '原始 JSON',
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
          label: '规划',
          purpose: '生成任务计划并选择模式路由。',
          steps: {
            overview: { label: '规划路由', summary: '选择发现、匹配或集成执行路径。' },
          },
        },
        Profiling: {
          label: '画像',
          purpose: '抽取表和列元数据。',
          steps: {
            overview: { label: '表画像', summary: '读取表形状、列、类型和值统计。' },
          },
        },
        Retrieval: {
          label: '检索',
          purpose: '通过 TLCF 级联缩小数据湖候选范围。',
          steps: {
            L1: { label: '词法过滤', summary: '使用表文本和模式关键词保留可能候选。' },
            L2: { label: '向量召回', summary: '查询嵌入，找回语义相近的表。' },
            L3: { label: 'LLM 重排', summary: '让 LLM 重排最强候选。' },
          },
        },
        Matcher: {
          label: '匹配',
          purpose: '验证列对齐并生成最终映射。',
          steps: {
            filtering: { label: '候选过滤', summary: '在高成本验证前保留可能的列对。' },
            LLM: { label: 'LLM 验证', summary: '检查候选列对的语义等价性。' },
            decision: { label: '一对一决策', summary: '选择最终无冲突的列映射。' },
          },
        },
      },
    },
  },
}

export function getWorkspaceCopy(language: Language = 'en'): WorkspaceCopy {
  return workspaceCopy[language]
}
