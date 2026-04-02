import { Alert, Box, Button, Chip, CircularProgress, Stack, Typography } from '@mui/material'
import InsightsOutlinedIcon from '@mui/icons-material/InsightsOutlined'
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined'
import { useCallback, useEffect, useRef, useState } from 'react'

export type AgriRelationsResponse = {
  analysis?: any
  llm_base_url?: string
  llm_model?: string
  error?: string
  raw?: string
}

export type AgriRelationsHookOptions = {
  chunkId?: number | null
  savedAnalysis?: AgriRelationsResponse | null
  savedAnalyzedAt?: string | null
  onPersisted?: (detail: Record<string, unknown>) => void
}

export function useAgriRelations(text: string, options?: AgriRelationsHookOptions) {
  const { chunkId, savedAnalysis, savedAnalyzedAt, onPersisted } = options ?? {}
  const [state, setState] = useState<AgriRelationsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const savedRef = useRef(savedAnalysis)
  savedRef.current = savedAnalysis

  useEffect(() => {
    setState(savedRef.current ?? null)
  }, [chunkId, savedAnalyzedAt])

  const run = useCallback(async () => {
    const t = text.trim()
    if (!t) return
    setLoading(true)
    try {
      if (chunkId != null) {
        const r = await fetch(`/api/ner/chunks/${chunkId}/agri`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: t }),
        })
        const data = (await r.json()) as Record<string, unknown> & {
          error?: string
          agri_analysis?: AgriRelationsResponse | null
        }
        if (!r.ok) {
          setState({ error: String(data?.error ?? `Request failed (${r.status})`) })
          return
        }
        const ag = data.agri_analysis as AgriRelationsResponse | undefined
        if (ag?.analysis) {
          setState(ag)
          onPersisted?.(data)
        } else {
          setState({ error: data?.error ?? 'No analysis in response' })
        }
        return
      }

      const r = await fetch('/api/llm/agri-relations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: t }),
      })
      const data = (await r.json()) as AgriRelationsResponse
      setState(data)
    } catch (e) {
      setState({ error: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }, [text, chunkId, onPersisted])

  return { state, loading, run }
}

export function AgriRelationsResults(props: {
  state: AgriRelationsResponse | null
  loading?: boolean
}) {
  const { state, loading } = props

  if (loading && !state?.analysis && !state?.error) {
    return (
      <Stack direction="row" alignItems="center" gap={1} sx={{ py: 1 }}>
        <CircularProgress size={18} />
        <Typography variant="body2" color="text.secondary">
          Analyzing…
        </Typography>
      </Stack>
    )
  }

  return (
    <Box>
      {state?.error && (
        <Alert severity="warning" sx={{ mt: 0 }}>
          {state.error}
        </Alert>
      )}

      {state?.analysis && (
        <Box
          sx={{
            mt: 1,
            p: 1.25,
            borderRadius: 1,
            border: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
          }}
        >
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Relationship summary
          </Typography>
          <Typography variant="body2" sx={{ mb: 1, opacity: 0.9 }}>
            {String(state.analysis?.summary ?? '')}
          </Typography>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} flexWrap="wrap">
            {(state.analysis?.factors ?? []).length > 0 && (
              <Box>
                <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                  Factors (causes)
                </Typography>
                <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                  {(state.analysis?.factors ?? []).map((f: any, i: number) => (
                    <Chip
                      key={i}
                      size="small"
                      label={f?.name ?? 'unknown'}
                      title={f?.type ? String(f.type) : undefined}
                    />
                  ))}
                </Stack>
              </Box>
            )}

            {(state.analysis?.targets ?? []).length > 0 && (
              <Box>
                <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                  Targets (crops/livestock)
                </Typography>
                <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                  {(state.analysis?.targets ?? []).map((t: any, i: number) => (
                    <Chip
                      key={i}
                      size="small"
                      label={t?.name ?? 'unknown'}
                      title={t?.type ? String(t.type) : undefined}
                    />
                  ))}
                </Stack>
              </Box>
            )}

            {(state.analysis?.actors ?? []).length > 0 && (
              <Box>
                <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                  Actors (who acts)
                </Typography>
                <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                  {(state.analysis?.actors ?? []).map((a: any, i: number) => (
                    <Chip
                      key={i}
                      size="small"
                      label={a?.name ?? 'unknown'}
                      title={a?.type ? String(a.type) : undefined}
                    />
                  ))}
                </Stack>
              </Box>
            )}
          </Stack>

          {(state.analysis?.problems ?? []).length > 0 && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                Problems
              </Typography>
              <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                {(state.analysis?.problems ?? []).map((p: any, i: number) =>
                  typeof p === 'string' ? (
                    <Chip key={i} size="small" label={p} />
                  ) : (
                    <Chip
                      key={i}
                      size="small"
                      label={p?.name ?? p?.text ?? 'unknown'}
                      title={p?.type ? String(p.type) : undefined}
                    />
                  ),
                )}
              </Stack>
            </Box>
          )}

          {(state.analysis?.solutions ?? []).length > 0 && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                Solutions (actions)
              </Typography>
              <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                {(state.analysis?.solutions ?? []).map((sln: any, i: number) => (
                  <Chip
                    key={i}
                    size="small"
                    label={sln?.name ?? 'unknown'}
                    title={sln?.category ? String(sln.category) : undefined}
                  />
                ))}
              </Stack>
            </Box>
          )}

          {(state.analysis?.impacts ?? []).length > 0 && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                Impacts (cause → result)
              </Typography>
              <Stack component="ul" sx={{ m: 0, mt: 0.5, pl: 2 }} spacing={0.4}>
                {(state.analysis?.impacts ?? []).map((imp: any, i: number) => (
                  <li key={i}>
                    <Typography variant="caption">
                      <strong>{imp?.from ?? '?'}</strong> → <strong>{imp?.to ?? '?'}</strong> (
                      {imp?.effect ?? 'khong_ro'})
                      {imp?.evidence ? ` — evidence: ${String(imp.evidence)}` : ''}
                    </Typography>
                  </li>
                ))}
              </Stack>
            </Box>
          )}

          {state.analysis?.outcome && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                Outcome
              </Typography>
              <Typography variant="caption" display="block">
                {String(state.analysis?.outcome?.result ?? 'khong_ro')}
                {state.analysis?.outcome?.reason
                  ? ` — ${String(state.analysis?.outcome?.reason)}`
                  : ''}
              </Typography>
            </Box>
          )}
        </Box>
      )}
    </Box>
  )
}

type AgriRelationsPanelProps = {
  text: string
  chunkId?: number | null
  /** When bound to a saved chunk, true if DB already has a stored analysis */
  hasSavedAnalysis?: boolean
  /** Optional: preloaded snapshot (e.g. from GET /chunks/:id) so saved results show before re-run */
  savedAnalysis?: AgriRelationsResponse | null
  savedAnalyzedAt?: string | null
  onPersisted?: (detail: Record<string, unknown>) => void
}

export function AgriRelationsPanel(props: AgriRelationsPanelProps) {
  const { text, chunkId, hasSavedAnalysis, onPersisted, savedAnalysis, savedAnalyzedAt } = props
  const agri = useAgriRelations(text, { chunkId, onPersisted, savedAnalysis, savedAnalyzedAt })

  const runLabel =
    chunkId != null
      ? hasSavedAnalysis
        ? 'Refresh analysis'
        : 'Run analysis & save'
      : 'Run analysis'

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
        Analyze agri relations
      </Typography>
      <Button
        size="small"
        variant="contained"
        onClick={() => void agri.run()}
        disabled={agri.loading || !text.trim()}
        startIcon={
          agri.loading ? (
            <CircularProgress size={16} />
          ) : chunkId != null && hasSavedAnalysis ? (
            <RefreshOutlinedIcon fontSize="small" />
          ) : (
            <InsightsOutlinedIcon fontSize="small" />
          )
        }
      >
        {agri.loading ? <span>Analyzing…</span> : runLabel}
      </Button>

      <AgriRelationsResults state={agri.state} loading={agri.loading} />
    </Box>
  )
}
