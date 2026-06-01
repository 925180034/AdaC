import { apiJson } from './client'

export type RuntimeBackend = 'local' | 'api'
export type LocalRuntimeStatus = 'stopped' | 'starting' | 'ready' | 'stopping' | 'error'

export type LlmRuntimeInfo = {
  backend: RuntimeBackend
  base_url: string
  model: string
  api_key_configured: boolean
  local_status: LocalRuntimeStatus
  local_ready: boolean
  local_last_error: string | null
}

export function getLlmRuntime(tenantId: string): Promise<LlmRuntimeInfo> {
  return apiJson<LlmRuntimeInfo>('/runtime/llm', tenantId)
}

export function updateLlmRuntime(tenantId: string, backend: RuntimeBackend): Promise<LlmRuntimeInfo> {
  return apiJson<LlmRuntimeInfo>('/runtime/llm', tenantId, {
    method: 'PUT',
    body: JSON.stringify({ backend }),
  })
}
