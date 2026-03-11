export type NerEntity = {
  text: string
  label: string
  score?: number
  start?: number
  end?: number
}

export type NerChunkSpan = {
  index: number
  start: number
  end: number
  original_text?: string
  corrected_text?: string
}

export type NerResponse = {
  model?: string
  text_used?: string
  entities?: NerEntity[]
  cached_labels?: boolean
  took_ms?: number
  chunks_used?: number
  chunks?: NerChunkSpan[]
  chunking_strategy?: string
  use_spell_correction?: boolean
  error?: string
}

export const SUPPORTED_MODELS = [
  'urchade/gliner_multi-v2.1',
  'knowledgator/gliner-bi-base-v2.0',
  'knowledgator/gliner-qwen-0.5B-v1.0',
  'knowledgator/gliner-qwen-1.5B-v1.0',
] as const

export type SupportedModel = (typeof SUPPORTED_MODELS)[number]

