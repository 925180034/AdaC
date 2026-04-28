import { describe, expect, it } from 'vitest'
import { buildHeaders, joinUrl } from './client'

describe('API client helpers', () => {
  it('joins base URL and path without duplicate slash', () => {
    expect(joinUrl('http://localhost:8080/', '/tables')).toBe('http://localhost:8080/tables')
    expect(joinUrl('http://localhost:8080//', '//tasks/task-1')).toBe(
      'http://localhost:8080/tasks/task-1',
    )
  })

  it('builds auth and tenant headers', () => {
    expect(buildHeaders('tenant-a')).toMatchObject({
      Authorization: 'Bearer dev-local-token',
      'X-Tenant-Id': 'tenant-a',
    })
  })
})
