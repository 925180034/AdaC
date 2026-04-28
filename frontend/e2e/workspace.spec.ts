import { expect, test } from '@playwright/test'

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
        }),
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
  await expect(page.getByLabel('Mode')).toHaveValue('integrate')
  await expect(page.getByLabel('Query table')).toHaveValue('toy_source')
  await expect(page.getByRole('button', { name: 'Run AdaCascade' })).toBeEnabled()
  await expect(page.getByText('No active task')).toBeVisible()
  await expect(page.getByText(/This preview intentionally does not auto-run\./)).toBeVisible()
  expect(taskStartRequests).toBe(0)
})
