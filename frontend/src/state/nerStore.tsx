import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { NerResponse, SupportedModel } from '../types/ner'
import { SUPPORTED_MODELS } from '../types/ner'
import { DEFAULT_LABELS, DEFAULT_TEXT } from '../features/ner/constants'

type NerStoreState = {
  model: SupportedModel
  text: string
  labels: string[]
  threshold: number
  chunkingMode: 'none' | 'semantic' | 'token' | 'recursive'
  chunkCharThreshold: number
  chunkSizeTokens: number
  useSpellCorrection: boolean
  multiLabel: boolean
  loading: boolean
  error: string | null
  resp: NerResponse | null
}

type NerStoreActions = {
  setModel: (m: SupportedModel) => void
  setText: (t: string) => void
  setLabels: (labels: string[]) => void
  setThreshold: (t: number) => void
  setChunkingMode: (m: NerStoreState['chunkingMode']) => void
  setChunkCharThreshold: (n: number) => void
  setChunkSizeTokens: (n: number) => void
  setUseSpellCorrection: (v: boolean) => void
  setMultiLabel: (v: boolean) => void
  resetExample: () => void
  extract: (textOverride?: string) => Promise<void>
}

const NerStoreContext = createContext<{ state: NerStoreState; actions: NerStoreActions } | null>(
  null
)

export function NerStoreProvider(props: { children: React.ReactNode }) {
  const [model, setModel] = useState<SupportedModel>(SUPPORTED_MODELS[0])
  const [text, setText] = useState(DEFAULT_TEXT)
  const [labels, setLabels] = useState<string[]>([...DEFAULT_LABELS])
  const [threshold, setThreshold] = useState(0.3)
  const [chunkingMode, setChunkingMode] = useState<NerStoreState['chunkingMode']>('semantic')
  const [chunkCharThreshold, setChunkCharThreshold] = useState(0)
  const [chunkSizeTokens, setChunkSizeTokens] = useState(256)
  const [useSpellCorrection, setUseSpellCorrection] = useState(false)
  const [multiLabel, setMultiLabel] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resp, setResp] = useState<NerResponse | null>(null)

  const resetExample = useCallback(() => {
    setText(DEFAULT_TEXT)
    setLabels([...DEFAULT_LABELS])
  }, [])

  const extract = useCallback(async (textOverride?: string) => {
    const textForNer = typeof textOverride === 'string' ? textOverride : text
    setLoading(true)
    setError(null)
    setResp(null)
    try {
      const r = await fetch('/api/ner', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model,
          text: textForNer,
          labels,
          threshold,
          use_chunking: chunkingMode !== 'none',
          chunking_strategy: chunkingMode === 'none' ? 'semantic' : chunkingMode,
          chunk_char_threshold: chunkCharThreshold,
          chunk_size_tokens: chunkSizeTokens,
          use_spell_correction: useSpellCorrection,
          multi_label: multiLabel,
          use_cache: true,
        }),
      })

      const data = (await r.json()) as NerResponse
      if (!r.ok) throw new Error(data?.error || `Request failed (${r.status})`)
      setResp(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [
    chunkCharThreshold,
    chunkSizeTokens,
    chunkingMode,
    labels,
    model,
    text,
    threshold,
    useSpellCorrection,
    multiLabel,
  ])

  const state = useMemo<NerStoreState>(
    () => ({
      model,
      text,
      labels,
      threshold,
      chunkingMode,
      chunkCharThreshold,
      chunkSizeTokens,
      useSpellCorrection,
      multiLabel,
      loading,
      error,
      resp,
    }),
    [
      chunkCharThreshold,
      chunkSizeTokens,
      chunkingMode,
      error,
      labels,
      loading,
      model,
      resp,
      text,
      threshold,
      useSpellCorrection,
      multiLabel,
    ]
  )

  const actions = useMemo<NerStoreActions>(
    () => ({
      setModel,
      setText,
      setLabels,
      setThreshold,
      setChunkingMode,
      setChunkCharThreshold,
      setChunkSizeTokens,
      setUseSpellCorrection,
      setMultiLabel,
      resetExample,
      extract,
    }),
    [extract, resetExample]
  )

  return <NerStoreContext.Provider value={{ state, actions }}>{props.children}</NerStoreContext.Provider>
}

export function useNerStore() {
  const ctx = useContext(NerStoreContext)
  if (!ctx) throw new Error('useNerStore must be used within NerStoreProvider')
  return ctx
}

