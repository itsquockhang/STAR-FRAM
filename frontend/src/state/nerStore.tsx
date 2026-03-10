import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { NerResponse, SupportedModel } from '../types/ner'
import { SUPPORTED_MODELS } from '../types/ner'
import { DEFAULT_LABELS, DEFAULT_TEXT } from '../features/ner/constants'

type NerStoreState = {
  model: SupportedModel
  text: string
  labels: string[]
  threshold: number
  chunkingMode: 'none' | 'semantic' | 'token' | 'sentence'
  useSpellCorrection: boolean
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
  setUseSpellCorrection: (v: boolean) => void
  resetExample: () => void
  extract: () => Promise<void>
}

const NerStoreContext = createContext<{ state: NerStoreState; actions: NerStoreActions } | null>(
  null
)

export function NerStoreProvider(props: { children: React.ReactNode }) {
  const [model, setModel] = useState<SupportedModel>(SUPPORTED_MODELS[0])
  const [text, setText] = useState(DEFAULT_TEXT)
  const [labels, setLabels] = useState<string[]>([...DEFAULT_LABELS])
  const [threshold, setThreshold] = useState(0.3)
  const [chunkingMode, setChunkingMode] = useState<NerStoreState['chunkingMode']>('token')
  const [useSpellCorrection, setUseSpellCorrection] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resp, setResp] = useState<NerResponse | null>(null)

  const resetExample = useCallback(() => {
    setText(DEFAULT_TEXT)
    setLabels([...DEFAULT_LABELS])
  }, [])

  const extract = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResp(null)
    try {
      const r = await fetch('/api/ner', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model,
          text,
          labels,
          threshold,
          use_chunking: chunkingMode !== 'none',
          chunking_strategy: chunkingMode === 'none' ? 'semantic' : chunkingMode,
          use_spell_correction: useSpellCorrection,
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
  }, [chunkingMode, labels, model, text, threshold, useSpellCorrection])

  const state = useMemo<NerStoreState>(
    () => ({
      model,
      text,
      labels,
      threshold,
      chunkingMode,
      useSpellCorrection,
      loading,
      error,
      resp,
    }),
    [chunkingMode, error, labels, loading, model, resp, text, threshold, useSpellCorrection]
  )

  const actions = useMemo<NerStoreActions>(
    () => ({
      setModel,
      setText,
      setLabels,
      setThreshold,
      setChunkingMode,
      setUseSpellCorrection,
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

