import { expect, test, type Page, type Route } from '@playwright/test'

const tablesResponse = {
  items: [
    {
      table_id: 'toy_source',
      tenant_id: 'default',
      table_name: 'Toy Source',
      status: 'READY',
      row_count: 12,
      col_count: 4,
      uploaded_at: '2026-04-28T00:00:00Z',
    },
    {
      table_id: 'toy_target',
      tenant_id: 'default',
      table_name: 'Toy Target',
      status: 'READY',
      row_count: 10,
      col_count: 5,
      uploaded_at: '2026-04-28T00:00:01Z',
    },
  ],
  total: 2,
  limit: 200,
  offset: 0,
}

function taskDetail(taskId: string, taskType: 'DISCOVER_ONLY' | 'MATCH_ONLY' | 'INTEGRATE') {
  return {
    task_id: taskId,
    tenant_id: 'default',
    task_type: taskType,
    query_table_id: 'toy_source',
    target_table_id: taskType === 'MATCH_ONLY' ? 'toy_target' : null,
    status: 'SUCCESS',
    submitted_at: '2026-04-28T00:00:02Z',
    finished_at: '2026-04-28T00:00:03Z',
    error_message: null,
    plan_config: {},
    trace: [],
    ranking: taskType === 'MATCH_ONLY' ? [] : [
      {
        rank: 1,
        candidate_table: 'toy_target',
        score: 0.92,
        layer_scores: { s1: 0.81, s2: 0.88, s3: 0.94 },
      },
    ],
    mappings: taskType === 'DISCOVER_ONLY' ? [] : [
      {
        mapping_id: 'mapping-1',
        src_column_id: 'toy_source.name',
        tgt_column_id: 'toy_target.full_name',
        scenario: 'SMD',
        confidence: 0.89,
        is_matched: true,
        reasoning: 'same semantic column',
        created_at: '2026-04-28T00:00:03Z',
      },
    ],
  }
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
}

async function mockRunnableBackend(page: Page) {
  let runtimeBackend: 'local' | 'api' = 'local'

  await page.route('http://localhost:8080/**', async (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/tables') {
      await fulfillJson(route, tablesResponse)
      return
    }

    if (url.pathname === '/runtime/llm') {
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON() as { backend?: 'local' | 'api' }
        runtimeBackend = body.backend ?? runtimeBackend
      }

      await fulfillJson(route, {
        backend: runtimeBackend,
        base_url: runtimeBackend === 'local' ? 'http://localhost:8000/v1' : 'https://api.deepseek.com/v1',
        model: runtimeBackend === 'local' ? 'qwen3.5:9b-awq' : 'deepseek-chat',
        api_key_configured: true,
      })
      return
    }

    if (url.pathname === '/discover' || url.pathname === '/match' || url.pathname === '/integrate') {
      const taskId = `${url.pathname.slice(1)}-task`
      await fulfillJson(route, { task_id: taskId, status: 'RUNNING', state: { status: 'RUNNING' } })
      return
    }

    const taskMatch = url.pathname.match(/^\/tasks\/(.+)$/)
    if (taskMatch && !url.pathname.endsWith('/events')) {
      const taskId = taskMatch[1]
      const taskType = taskId.startsWith('discover') ? 'DISCOVER_ONLY' : taskId.startsWith('match') ? 'MATCH_ONLY' : 'INTEGRATE'
      await fulfillJson(route, taskDetail(taskId, taskType))
      return
    }

    if (url.pathname.endsWith('/events')) {
      const taskId = url.pathname.split('/')[2]
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          `event: agent_completed\ndata: {"task_id":"${taskId}","type":"agent_completed","agent":"Planner","status":"SUCCESS","output_size":1,"timestamp":"2026-04-28T00:00:01Z"}`,
          `event: agent_completed\ndata: {"task_id":"${taskId}","type":"agent_completed","agent":"Profiling","status":"SUCCESS","output_size":1,"timestamp":"2026-04-28T00:00:02Z"}`,
          `event: agent_started\ndata: {"task_id":"${taskId}","type":"agent_started","agent":"Retrieval","layer":"L1","status":"RUNNING","timestamp":"2026-04-28T00:00:02Z"}`,
          `event: agent_completed\ndata: {"task_id":"${taskId}","type":"agent_completed","agent":"Retrieval","layer":"L1","status":"SUCCESS","output_size":1,"timestamp":"2026-04-28T00:00:02Z"}`,
          `event: agent_completed\ndata: {"task_id":"${taskId}","type":"agent_completed","agent":"Retrieval","layer":"L2","status":"SUCCESS","output_size":1,"timestamp":"2026-04-28T00:00:02Z"}`,
          `event: agent_completed\ndata: {"task_id":"${taskId}","type":"agent_completed","agent":"Retrieval","layer":"L3","status":"SUCCESS","output_size":1,"timestamp":"2026-04-28T00:00:03Z"}`,
          `event: agent_completed\ndata: {"task_id":"${taskId}","type":"agent_completed","agent":"Matcher","layer":"filtering","status":"SUCCESS","output_size":1,"timestamp":"2026-04-28T00:00:03Z"}`,
          `event: agent_completed\ndata: {"task_id":"${taskId}","type":"agent_completed","agent":"Matcher","layer":"LLM","status":"SUCCESS","output_size":1,"timestamp":"2026-04-28T00:00:03Z"}`,
          `event: agent_completed\ndata: {"task_id":"${taskId}","type":"agent_completed","agent":"Matcher","layer":"decision","status":"SUCCESS","output_size":1,"timestamp":"2026-04-28T00:00:03Z"}`,
          `event: task_completed\ndata: {"task_id":"${taskId}","type":"task_completed","status":"SUCCESS","timestamp":"2026-04-28T00:00:03Z"}`,
          '',
        ].join('\n\n'),
      })
      return
    }

    throw new Error(`Unexpected backend request: ${route.request().url()}`)
  })
}

async function expectFourAgentPanel(page: Page) {
  const agentCards = page.locator('.agent-card')
  await expect(agentCards).toHaveCount(4)

  await expect(page.getByRole('article', { name: 'Planner' })).toBeVisible()
  await expect(page.getByRole('article', { name: 'Profiling' })).toBeVisible()
  await expect(page.getByRole('article', { name: 'Retrieval' })).toBeVisible()
  await expect(page.getByRole('article', { name: 'Matcher' })).toBeVisible()

  await expect(page.getByText('Plan routing')).toBeVisible()
  await expect(page.getByText('Table profiling')).toBeVisible()
  await expect(page.getByText('Lexical filter')).toBeVisible()
  await expect(page.getByText('Vector recall')).toBeVisible()
  await expect(page.getByText('LLM rerank')).toBeVisible()
  await expect(page.getByText('Candidate filter')).toBeVisible()
  await expect(page.getByText('LLM verification')).toBeVisible()
  await expect(page.getByText('One-to-one decision')).toBeVisible()
}

test.describe('workspace task execution', () => {
  test.beforeEach(async ({ page }) => {
    await mockRunnableBackend(page)
  })

  test('loads default light theme and switches language, theme, and runtime', async ({ page }) => {
    await page.goto('/workspace?tenant_id=default&mode=integrate&query_table_id=toy_source')

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
    await expect(page.getByRole('heading', { name: 'AdaCascade Workbench' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Run AdaCascade' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Local model' })).toHaveAttribute('aria-pressed', 'true')

    await page.getByRole('button', { name: '中文' }).click()
    await expect(page.getByRole('heading', { name: 'AdaCascade 工作台' })).toBeVisible()
    await expect(page.getByRole('button', { name: '运行 AdaCascade' })).toBeVisible()
    await expect(page.getByLabel('模式')).toBeVisible()
    await expect(page.getByText('暂无活跃任务')).toBeVisible()

    await page.getByRole('button', { name: '深色' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

    await page.getByRole('button', { name: 'API 模型' }).click()
    await expect(page.getByRole('button', { name: 'API 模型' })).toHaveAttribute('aria-pressed', 'true')
  })

  test('starts discover and displays ranking results', async ({ page }) => {
    await page.goto('/workspace?tenant_id=default&mode=discover&query_table_id=toy_source')
    await page.getByRole('button', { name: 'Run AdaCascade' }).click()

    await expect(page.getByText('Task discover-task')).toBeVisible()
    await expectFourAgentPanel(page)
    await page.getByRole('tab', { name: 'Ranking' }).click()
    await expect(page.getByRole('tabpanel', { name: 'Ranking' })).toContainText('toy_target')
  })

  test('starts match and displays mapping results', async ({ page }) => {
    await page.goto('/workspace?tenant_id=default&mode=match&source_table_id=toy_source&target_table_id=toy_target')
    await page.getByRole('button', { name: 'Run AdaCascade' }).click()

    await expect(page.getByText('Task match-task')).toBeVisible()
    await expectFourAgentPanel(page)
    await page.getByRole('tab', { name: 'Mappings' }).click()
    await expect(page.getByRole('tabpanel', { name: 'Mappings' })).toContainText('toy_source.name')
  })

  test('starts integrate and displays ranking and mapping results', async ({ page }) => {
    await page.goto('/workspace?tenant_id=default&mode=integrate&query_table_id=toy_source')
    await page.getByRole('button', { name: 'Run AdaCascade' }).click()

    await expect(page.getByText('Task integrate-task')).toBeVisible()
    await expectFourAgentPanel(page)
    await page.getByRole('tab', { name: 'Ranking' }).click()
    await expect(page.getByRole('tabpanel', { name: 'Ranking' })).toContainText('toy_target')
    await page.getByRole('tab', { name: 'Mappings' }).click()
    await expect(page.getByRole('tabpanel', { name: 'Mappings' })).toContainText('toy_target.full_name')
  })
})

test('prefills workspace context from route params without auto-running a task', async ({ page }) => {
  let taskStartRequests = 0

  await page.route('http://localhost:8080/**', async (route) => {
    const requestUrl = route.request().url()
    const url = new URL(requestUrl)

    if (url.pathname === '/tables') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            ...tablesResponse.items,
          ],
          total: 2,
          limit: 200,
          offset: 0,
        }),
      })
      return
    }

    if (url.pathname === '/runtime/llm') {
      await fulfillJson(route, {
        backend: 'local',
        base_url: 'http://localhost:8000/v1',
        model: 'qwen3.5:9b-awq',
        api_key_configured: true,
      })
      return
    }

    if (['/discover', '/integrate', '/match'].includes(url.pathname) || url.pathname.startsWith('/tasks/')) {
      taskStartRequests += 1
      await route.abort()
      return
    }

    throw new Error(`Unexpected backend request during prefill smoke test: ${requestUrl}`)
  })

  await page.goto('/workspace?tenant_id=default&mode=integrate&query_table_id=toy_source')

  await expect(page.getByRole('heading', { name: 'AdaCascade Workbench' })).toBeVisible()
  await expect(page.locator('#task-mode')).toHaveValue('integrate')
  await expect(page.locator('#query-table')).toHaveValue('toy_source')
  await expect(page.getByRole('button', { name: 'Run AdaCascade' })).toBeEnabled()
  await expect(page.getByText('No active task')).toBeVisible()
  await expect(page.getByText(/This preview intentionally does not auto-run\./)).toBeVisible()
  expect(taskStartRequests).toBe(0)
})
