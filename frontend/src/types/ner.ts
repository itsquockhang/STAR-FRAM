export type NerEntity = {
  text: string
  label: string
  score?: number
  start?: number
  end?: number
}

export type NerResponse = {
  model?: string
  entities?: NerEntity[]
  cached_labels?: boolean
  took_ms?: number
  chunks_used?: number
  error?: string
}

export const SUPPORTED_MODELS = [
  'urchade/gliner_multi-v2.1',
  'knowledgator/gliner-bi-base-v2.0',
] as const

export type SupportedModel = (typeof SUPPORTED_MODELS)[number]

