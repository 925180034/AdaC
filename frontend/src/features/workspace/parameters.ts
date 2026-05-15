export type ExecutionProfile = 'reproducible' | 'fast' | 'joinTuned'

export type AdvancedParameters = {
  theta_1: number
  theta_2: number
  theta_3: number
  theta_match: number
  matcher_top_k: number
}

export const PAPER_PARAMETER_DEFAULTS: AdvancedParameters = {
  theta_1: 0.2,
  theta_2: 0.55,
  theta_3: 0.5,
  theta_match: 0.7,
  matcher_top_k: 3,
}
