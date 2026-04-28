const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'
const apiKey = import.meta.env.VITE_API_KEY ?? 'dev-local-token'

export const API_BASE_URL = apiBaseUrl
export const API_KEY = apiKey

export function joinUrl(baseUrl: string, path: string): string {
  const trimmedBase = baseUrl.replace(/\/+$/, '')
  const trimmedPath = path.replace(/^\/+/, '')
  return `${trimmedBase}/${trimmedPath}`
}

export function buildHeaders(tenantId: string): Record<string, string> {
  return {
    Authorization: `Bearer ${apiKey}`,
    'X-Tenant-Id': tenantId,
  }
}

async function errorText(response: Response): Promise<string> {
  const text = await response.text()
  if (!text) {
    return `Request failed with ${response.status} ${response.statusText}`.trim()
  }

  try {
    const parsed = JSON.parse(text) as { detail?: unknown; message?: unknown }
    const detail = parsed.detail ?? parsed.message
    if (typeof detail === 'string') {
      return `Request failed with ${response.status}: ${detail}`
    }
  } catch {
    return `Request failed with ${response.status}: ${text}`
  }

  return `Request failed with ${response.status}: ${text}`
}

export async function apiJson<T>(
  path: string,
  tenantId: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(joinUrl(apiBaseUrl, path), {
    ...init,
    headers: {
      ...buildHeaders(tenantId),
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  })

  if (!response.ok) {
    throw new Error(await errorText(response))
  }

  return (await response.json()) as T
}
