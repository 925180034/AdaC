import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createDataset, listDatasets, uploadDatasetTables } from './datasets'

const fetchMock = vi.fn()

describe('Dataset API client', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  it('lists tenant-scoped Datasets', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    })

    await listDatasets('tenant-a')

    expect(fetchMock).toHaveBeenCalledWith('/datasets', expect.objectContaining({
      headers: expect.objectContaining({
        Authorization: 'Bearer dev-local-token',
        'X-Tenant-Id': 'tenant-a',
        'Content-Type': 'application/json',
      }),
    }))
  })

  it('creates a Dataset with JSON payload', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ dataset_id: 'dataset-a' }),
    })

    await createDataset('tenant-a', { dataset_name: 'Lake A', description: 'demo' })

    expect(fetchMock).toHaveBeenCalledWith('/datasets', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ dataset_name: 'Lake A', description: 'demo' }),
    }))
  })

  it('uploads files with FormData and no JSON content type', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ accepted: [], rejected: [], skipped: [] }),
    })
    const file = new File(['id,name\n1,Ada\n'], 'people.csv', { type: 'text/csv' })

    await uploadDatasetTables('tenant-a', 'dataset-a', [file], { uploadedBy: 'tester', tableNamePrefix: 'demo' })

    const [, init] = fetchMock.mock.calls[0]
    expect(fetchMock).toHaveBeenCalledWith('/datasets/dataset-a/tables', expect.objectContaining({ method: 'POST' }))
    expect(init.headers).toEqual({
      Authorization: 'Bearer dev-local-token',
      'X-Tenant-Id': 'tenant-a',
    })
    expect(init.body).toBeInstanceOf(FormData)
    expect(Array.from((init.body as FormData).getAll('files'))).toEqual([file])
    expect((init.body as FormData).get('uploaded_by')).toBe('tester')
    expect((init.body as FormData).get('table_name_prefix')).toBe('demo')
  })
})
