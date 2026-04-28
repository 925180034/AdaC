import type { Language } from './uiPreferences'

export type WorkspaceCopy = {
  page: {
    eyebrow: string
    title: string
    warningLabel: string
    warning: string
  }
  toolbar: {
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
    queryTable: string
    sourceTable: string
    targetTable: string
    run: string
    running: string
    note: string
  }
  results: {
    kicker: string
    title: string
    taskLabel: (taskId: string) => string
    viewsLabel: string
    tabs: Record<'graph' | 'ranking' | 'mappings' | 'raw', string>
    emptyTitle: string
    emptyDescription: string
    noLayerScores: string
    rankingAria: string
    rankingTitle: string
    candidates: (count: number) => string
    candidateScore: (rank: number) => string
    mappingsAria: string
    mappingsTitle: string
    alignments: (count: number) => string
    matched: string
    rejected: string
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
    eventsTitle: string
    eventsKicker: string
    defaultActor: string
    agentPurpose: Record<string, string>
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
      queryTable: 'Query table',
      sourceTable: 'Source table',
      targetTable: 'Target table',
      run: 'Run AdaCascade',
      running: 'Running AdaCascade…',
      note: 'Static shell preview. REST submission and SSE reconciliation will attach in the next task.',
    },
    results: {
      kicker: 'Central workspace',
      title: 'Result Workspace',
      taskLabel: (taskId) => `Task ${taskId}`,
      viewsLabel: 'Result views',
      tabs: { graph: 'Graph', ranking: 'Ranking', mappings: 'Mappings', raw: 'Raw JSON' },
      emptyTitle: 'No active task',
      emptyDescription:
        'Choose a mode and table context, then run AdaCascade to populate graph, ranking, mappings, and raw JSON views. This preview intentionally does not auto-run.',
      noLayerScores: 'No layer scores',
      rankingAria: 'Ranking results',
      rankingTitle: 'Ranking',
      candidates: (count) => `${count} candidates`,
      candidateScore: (rank) => `Candidate ${rank} score`,
      mappingsAria: 'Column mapping results',
      mappingsTitle: 'Mappings',
      alignments: (count) => `${count} alignments`,
      matched: 'Matched',
      rejected: 'Rejected',
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
      eventsTitle: 'Recent events',
      eventsKicker: 'supporting log',
      defaultActor: 'Task',
      agentPurpose: {
        Planner: 'Builds the task plan and mode routing.',
        Profiling: 'Extracts table and column metadata.',
        Retrieval: 'Narrows the lake with TLCF cascade.',
        Matcher: 'Verifies column alignments and final mappings.',
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
      queryTable: '查询表',
      sourceTable: '源表',
      targetTable: '目标表',
      run: '运行 AdaCascade',
      running: 'AdaCascade 运行中…',
      note: '静态外壳预览。REST 提交与 SSE 对账将在后续任务接入。',
    },
    results: {
      kicker: '中央工作区',
      title: '结果工作区',
      taskLabel: (taskId) => `任务 ${taskId}`,
      viewsLabel: '结果视图',
      tabs: { graph: '图谱', ranking: '排序', mappings: '映射', raw: '原始 JSON' },
      emptyTitle: '暂无活跃任务',
      emptyDescription: '选择模式和表上下文后运行 AdaCascade，即可查看图谱、排序、映射和原始 JSON。此预览不会自动运行。',
      noLayerScores: '暂无层级分数',
      rankingAria: '排序结果',
      rankingTitle: '排序',
      candidates: (count) => `${count} 个候选`,
      candidateScore: (rank) => `候选 ${rank} 分数`,
      mappingsAria: '列映射结果',
      mappingsTitle: '映射',
      alignments: (count) => `${count} 个对齐`,
      matched: '已匹配',
      rejected: '已拒绝',
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
      eventsTitle: '最近事件',
      eventsKicker: '辅助日志',
      defaultActor: '任务',
      agentPurpose: {
        Planner: '生成任务计划并选择模式路由。',
        Profiling: '抽取表和列元数据。',
        Retrieval: '通过 TLCF 级联缩小数据湖候选范围。',
        Matcher: '验证列对齐并生成最终映射。',
      },
    },
  },
}

export function getWorkspaceCopy(language: Language = 'en'): WorkspaceCopy {
  return workspaceCopy[language]
}
