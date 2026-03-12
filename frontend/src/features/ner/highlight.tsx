import { Alert, Box, Button, Chip, CircularProgress, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material'
import InsightsOutlinedIcon from '@mui/icons-material/InsightsOutlined'
import { useEffect, useMemo, useState } from 'react'
import type { NerChunkSpan, NerEntity } from '../../types/ner'

// Deterministic label colors (stable per label name)
const LABEL_COLORS = [
  '#e3f2fd',
  '#fce4ec',
  '#f3e5f5',
  '#e8eaf6',
  '#e0f2f1',
  '#fff8e1',
  '#fbe9e7',
  '#efebe9',
  '#eceff1',
  '#e8f5e9',
  '#fffde7',
  '#e0f7fa',
  '#f1f8e9',
  '#f9fbe7',
  '#e7e7e7',
  '#ffecb3',
  '#d1c4e9',
  '#b2dfdb',
  '#ffccbc',
  '#c5cae9',
  '#b3e5fc',
  '#dcedd2',
  '#ffecb3',
  '#cfd8dc',
]

export function getLabelColor(label: string): string {
  let n = 0
  for (let i = 0; i < label.length; i++) n = (n * 31 + label.charCodeAt(i)) >>> 0
  return LABEL_COLORS[n % LABEL_COLORS.length]
}

type TextSegment =
  | { type: 'plain'; text: string }
  | { type: 'highlight'; text: string; label: string }

type ChunkWithEntities = {
  index: number
  start: number
  end: number
  originalText?: string
  correctedText: string
  entities: NerEntity[]
}

type AgriRelationsResponse = {
  analysis?: any
  llm_base_url?: string
  llm_model?: string
  error?: string
  raw?: string
}

export function buildHighlightSegments(text: string, entities: NerEntity[]): TextSegment[] {
  const segments: TextSegment[] = []
  const len = text.length
  if (len === 0) return segments

  // Keep only entities with valid start/end; sort by start.
  const valid = entities
    .filter((e) => typeof e.start === 'number' && typeof e.end === 'number' && e.start < e.end)
    .sort((a, b) => (a.start as number) - (b.start as number))

  let lastEnd = 0
  for (const e of valid) {
    const s = Math.max(lastEnd, e.start as number)
    const end = Math.min(len, e.end as number)
    if (s >= end) continue

    if (s > lastEnd) segments.push({ type: 'plain', text: text.slice(lastEnd, s) })
    segments.push({ type: 'highlight', text: text.slice(s, end), label: e.label })
    lastEnd = end
  }

  if (lastEnd < len) segments.push({ type: 'plain', text: text.slice(lastEnd) })
  if (segments.length === 0) segments.push({ type: 'plain', text })

  return segments
}

export function HighlightedText(props: {
  text: string
  entities: NerEntity[]
  title?: string
  chunks?: NerChunkSpan[]
  showBeforeAfter?: boolean
}) {
  const { text, entities, title = 'Highlighted text', chunks, showBeforeAfter = true } = props
  const [openChunksModal, setOpenChunksModal] = useState(false)
  const [chunkAnalysis, setChunkAnalysis] = useState<Record<number, AgriRelationsResponse | null>>({})
  const [chunkLoading, setChunkLoading] = useState<Record<number, boolean>>({})
  const [entitiesOpen, setEntitiesOpen] = useState<Record<number, boolean>>({})

  // Reset "Analyze agri relations" results when user extracts NER again (chunks change)
  useEffect(() => {
    setChunkAnalysis({})
    setChunkLoading({})
    setEntitiesOpen({})
  }, [chunks])

  const segments = buildHighlightSegments(text, entities)
  const labelsInResult = Array.from(new Set(entities.map((e) => e.label)))

  const chunksWithEntities: ChunkWithEntities[] = useMemo(() => {
    if (!chunks || chunks.length === 0) return []
    return chunks.map((c) => {
      const start = c.start ?? 0
      const end = c.end ?? start
      const ents = entities.filter((e) => {
        const es = e.start ?? 0
        const ee = e.end ?? es
        return es >= start && ee <= end
      })
      return {
        index: c.index,
        start,
        end,
        originalText: c.original_text,
        correctedText: c.corrected_text ?? text.slice(start, end),
        entities: ents,
      }
    })
  }, [chunks, entities, text])

  const analyzeChunk = async (c: ChunkWithEntities) => {
    const idx = c.index
    setChunkLoading((prev) => ({ ...prev, [idx]: true }))
    try {
      const r = await fetch('/api/llm/agri-relations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: c.correctedText,
        }),
      })
      const data = (await r.json()) as AgriRelationsResponse
      setChunkAnalysis((prev) => ({ ...prev, [idx]: data }))
    } catch (e) {
      setChunkAnalysis((prev) => ({
        ...prev,
        [idx]: { error: e instanceof Error ? e.message : String(e) },
      }))
    } finally {
      setChunkLoading((prev) => ({ ...prev, [idx]: false }))
    }
  }

  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>

      <Box
        sx={{
          p: 1.5,
          bgcolor: 'grey.50',
          borderRadius: 1,
          border: '1px solid',
          borderColor: 'divider',
          maxHeight: 280,
          overflow: 'auto',
        }}
      >
        <Typography
          component="span"
          sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.7 }}
        >
          {segments.map((seg, i) =>
            seg.type === 'plain' ? (
              <span key={i}>{seg.text}</span>
            ) : (
              <Box
                key={i}
                component="span"
                sx={{
                  bgcolor: getLabelColor(seg.label),
                  px: 0.3,
                  borderRadius: 0.5,
                  border: '1px solid',
                  borderColor: getLabelColor(seg.label),
                }}
                title={seg.label}
              >
                {seg.text}
              </Box>
            )
          )}
        </Typography>
      </Box>

      {labelsInResult.length > 0 && (
        <Stack direction="row" flexWrap="wrap" gap={0.5} alignItems="center">
          <Typography variant="caption" sx={{ mr: 0.5, opacity: 0.8 }}>
            Legend:
          </Typography>
          {labelsInResult.map((l) => (
            <Chip
              key={l}
              size="small"
              label={l}
              sx={{
                bgcolor: getLabelColor(l),
                border: '1px solid',
                borderColor: 'divider',
              }}
            />
          ))}
        </Stack>
      )}

      {chunksWithEntities.length > 0 && (
        <>
          <Button
            size="small"
            variant="outlined"
            onClick={() => setOpenChunksModal(true)}
            sx={{ alignSelf: 'flex-start' }}
          >
            View entities by chunk ({chunksWithEntities.length})
          </Button>

          <Dialog
            open={openChunksModal}
            onClose={() => setOpenChunksModal(false)}
            fullWidth
            maxWidth="md"
          >
            <DialogTitle>Entities by chunk</DialogTitle>
            <DialogContent dividers>
              <Stack spacing={2}>
                {chunksWithEntities.map((c) => (
                  <Box
                    key={c.index}
                    sx={{
                      p: 1.5,
                      borderRadius: 1,
                      border: '1px solid',
                      borderColor: 'divider',
                      bgcolor: 'grey.50',
                    }}
                  >
                    <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                      Chunk {c.index + 1}{' '}
                      <Typography component="span" variant="caption" sx={{ opacity: 0.7 }}>
                        ({c.start} – {c.end})
                      </Typography>
                    </Typography>
                    {showBeforeAfter &&
                      typeof c.originalText === 'string' &&
                      c.originalText.trim() !== '' && (
                      <Box sx={{ mb: 1 }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                          Before
                        </Typography>
                        <Box
                          sx={{
                            mt: 0.5,
                            p: 1,
                            borderRadius: 1,
                            bgcolor: 'background.paper',
                            border: '1px solid',
                            borderColor: 'divider',
                            maxHeight: 100,
                            overflow: 'auto',
                          }}
                        >
                          <Typography
                            variant="body2"
                            sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.7 }}
                          >
                            {c.originalText}
                          </Typography>
                        </Box>
                      </Box>
                    )}
                    {showBeforeAfter && (
                      <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                        After
                      </Typography>
                    )}
                    <Box
                      sx={{
                        mt: 0.5,
                        mb: 1,
                        p: 1,
                        borderRadius: 1,
                        bgcolor: 'background.paper',
                        maxHeight: 140,
                        overflow: 'auto',
                      }}
                    >
                      <Typography
                        variant="body2"
                        component="span"
                        sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.7 }}
                      >
                        {buildHighlightSegments(
                          c.correctedText,
                          c.entities.map((e) => ({
                            ...e,
                            start: (e.start ?? 0) - c.start,
                            end: (e.end ?? 0) - c.start,
                          }))
                        ).map((seg, i) =>
                          seg.type === 'plain' ? (
                            <span key={i}>{seg.text}</span>
                          ) : (
                            <Box
                              key={i}
                              component="span"
                              sx={{
                                bgcolor: getLabelColor(seg.label),
                                px: 0.3,
                                borderRadius: 0.5,
                                border: '1px solid',
                                borderColor: getLabelColor(seg.label),
                              }}
                              title={seg.label}
                            >
                              {seg.text}
                            </Box>
                          )
                        )}
                      </Typography>
                    </Box>
                    <Box sx={{ mt: 0.5 }}>
                      <Button
                        size="small"
                        variant="text"
                        onClick={() =>
                          setEntitiesOpen((prev) => ({ ...prev, [c.index]: !prev[c.index] }))
                        }
                        sx={{ px: 0, minWidth: 0, textTransform: 'none' }}
                      >
                        Entities ({c.entities.length}) {entitiesOpen[c.index] ? '▲' : '▼'}
                      </Button>
                      {c.entities.length === 0 ? (
                        <Typography variant="caption" sx={{ display: 'block', opacity: 0.7 }}>
                          No entities in this chunk.
                        </Typography>
                      ) : (
                        <Collapse in={!!entitiesOpen[c.index]} timeout="auto" unmountOnExit>
                          <Stack
                            component="ul"
                            sx={{ m: 0, mt: 0.5, pl: 2, listStyle: 'disc' }}
                            spacing={0.3}
                          >
                            {c.entities.map((e, idx) => (
                              <li key={`${c.index}-${idx}`}>
                                <Typography variant="caption">
                                  <strong>{e.label}</strong>: {e.text}{' '}
                                  {typeof e.score === 'number' &&
                                    `(${(e.score * 100).toFixed(1)}%)`}
                                </Typography>
                              </li>
                            ))}
                          </Stack>
                        </Collapse>
                      )}
                    </Box>

                    <Box sx={{ mt: 1 }}>
                      <Button
                        size="small"
                        variant="contained"
                        onClick={() => analyzeChunk(c)}
                        disabled={!!chunkLoading[c.index]}
                      >
                        {chunkLoading[c.index] ? (
                          <Stack direction="row" alignItems="center" gap={1}>
                            <CircularProgress size={16} />
                            <span>Analyzing…</span>
                          </Stack>
                        ) : (
                          <>
                            <InsightsOutlinedIcon fontSize="small" sx={{ mr: 0.5 }} />
                            Analyze agri relations
                          </>
                        )}
                      </Button>
                    </Box>

                    {chunkAnalysis[c.index]?.error && (
                      <Alert severity="warning" sx={{ mt: 1 }}>
                        {chunkAnalysis[c.index]?.error}
                      </Alert>
                    )}

                    {chunkAnalysis[c.index]?.analysis && (
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
                          {String(chunkAnalysis[c.index]?.analysis?.summary ?? '')}
                        </Typography>

                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} flexWrap="wrap">
                          {(chunkAnalysis[c.index]?.analysis?.factors ?? []).length > 0 && (
                            <Box>
                              <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                                Factors (causes)
                              </Typography>
                              <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                                {(chunkAnalysis[c.index]?.analysis?.factors ?? []).map(
                                  (f: any, i: number) => (
                                    <Chip
                                      key={i}
                                      size="small"
                                      label={f?.name ?? 'unknown'}
                                      title={f?.type ? String(f.type) : undefined}
                                    />
                                  )
                                )}
                              </Stack>
                            </Box>
                          )}

                          {(chunkAnalysis[c.index]?.analysis?.targets ?? []).length > 0 && (
                            <Box>
                              <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                                Targets (crops/livestock)
                              </Typography>
                              <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                                {(chunkAnalysis[c.index]?.analysis?.targets ?? []).map(
                                  (t: any, i: number) => (
                                    <Chip
                                      key={i}
                                      size="small"
                                      label={t?.name ?? 'unknown'}
                                      title={t?.type ? String(t.type) : undefined}
                                    />
                                  )
                                )}
                              </Stack>
                            </Box>
                          )}

                          {(chunkAnalysis[c.index]?.analysis?.actors ?? []).length > 0 && (
                            <Box>
                              <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                                Actors (who acts)
                              </Typography>
                              <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                                {(chunkAnalysis[c.index]?.analysis?.actors ?? []).map(
                                  (a: any, i: number) => (
                                    <Chip
                                      key={i}
                                      size="small"
                                      label={a?.name ?? 'unknown'}
                                      title={a?.type ? String(a.type) : undefined}
                                    />
                                  )
                                )}
                              </Stack>
                            </Box>
                          )}
                        </Stack>

                        {(chunkAnalysis[c.index]?.analysis?.problems ?? []).length > 0 && (
                          <Box sx={{ mt: 1 }}>
                            <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                              Problems
                            </Typography>
                            <Stack component="ul" sx={{ m: 0, mt: 0.5, pl: 2 }} spacing={0.4}>
                              {(chunkAnalysis[c.index]?.analysis?.problems ?? []).map(
                                (p: any, i: number) => (
                                  <li key={i}>
                                    <Typography variant="caption">
                                      {String(p ?? '')}
                                    </Typography>
                                  </li>
                                )
                              )}
                            </Stack>
                          </Box>
                        )}

                        {(chunkAnalysis[c.index]?.analysis?.solutions ?? []).length > 0 && (
                          <Box sx={{ mt: 1 }}>
                            <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                              Solutions (actions)
                            </Typography>
                            <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                              {(chunkAnalysis[c.index]?.analysis?.solutions ?? []).map(
                                (sln: any, i: number) => (
                                  <Chip
                                    key={i}
                                    size="small"
                                    label={sln?.name ?? 'unknown'}
                                    title={sln?.category ? String(sln.category) : undefined}
                                  />
                                )
                              )}
                            </Stack>
                          </Box>
                        )}

                        {(chunkAnalysis[c.index]?.analysis?.impacts ?? []).length > 0 && (
                          <Box sx={{ mt: 1 }}>
                            <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                              Impacts (cause → result)
                            </Typography>
                            <Stack component="ul" sx={{ m: 0, mt: 0.5, pl: 2 }} spacing={0.4}>
                              {(chunkAnalysis[c.index]?.analysis?.impacts ?? []).map(
                                (imp: any, i: number) => (
                                  <li key={i}>
                                    <Typography variant="caption">
                                      <strong>{imp?.from ?? '?'}</strong> →{' '}
                                      <strong>{imp?.to ?? '?'}</strong> ({imp?.effect ?? 'khong_ro'})
                                      {imp?.evidence
                                        ? ` — evidence: ${String(imp.evidence)}`
                                        : ''}
                                    </Typography>
                                  </li>
                                )
                              )}
                            </Stack>
                          </Box>
                        )}

                        {chunkAnalysis[c.index]?.analysis?.outcome && (
                          <Box sx={{ mt: 1 }}>
                            <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                              Outcome
                            </Typography>
                            <Typography variant="caption" display="block">
                              {String(chunkAnalysis[c.index]?.analysis?.outcome?.result ?? 'khong_ro')}
                              {chunkAnalysis[c.index]?.analysis?.outcome?.reason
                                ? ` — ${String(chunkAnalysis[c.index]?.analysis?.outcome?.reason)}`
                                : ''}
                            </Typography>
                          </Box>
                        )}
                      </Box>
                    )}
                  </Box>
                ))}
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setOpenChunksModal(false)}>Close</Button>
            </DialogActions>
          </Dialog>
        </>
      )}
    </Stack>
  )
}

