import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputBase,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
  Chip,
} from '@mui/material'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import StarBorderOutlinedIcon from '@mui/icons-material/StarBorderOutlined'
import StarIcon from '@mui/icons-material/Star'
import DeleteOutlineOutlinedIcon from '@mui/icons-material/DeleteOutlineOutlined'
import EditOutlinedIcon from '@mui/icons-material/EditOutlined'
import { useEffect, useState } from 'react'
import { buildHighlightSegments, getLabelColor } from '../highlight'
import type { NerEntity } from '../../../types/ner'

type SavedChunkSummary = {
  id: number
  doc_title?: string | null
  model?: string | null
  chunk_index?: number | null
  start?: number | null
  end?: number | null
  corrected_text?: string | null
  is_starred?: number | boolean
  status?: string | null
  created_at?: string | null
  updated_at?: string | null
}

type SavedEntity = {
  id: number
  label: string
  text: string
  score?: number | null
  start?: number | null
  end?: number | null
}

type SavedChunkDetail = SavedChunkSummary & {
  text_used?: string | null
  original_text?: string | null
  corrected_text?: string | null
  entities: SavedEntity[]
}

function formatCreated(s: string | null | undefined): string {
  if (!s) return '—'
  try {
    const d = new Date(s)
    if (Number.isNaN(d.getTime())) return s
    return d.toLocaleString(undefined, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return s
  }
}

type SortKey = 'id' | 'doc_title' | 'chunk_index' | 'start' | 'created_at' | null
type SortDir = 'asc' | 'desc'

const EXCEL_GRID = {
  borderCollapse: 'collapse' as const,
  border: '1px solid',
  borderColor: 'divider',
  '& .MuiTableCell-root': {
    borderRight: '1px solid',
    borderColor: 'divider',
    py: 0.5,
    px: 1,
    fontSize: 13,
  },
  '& .MuiTableHead .MuiTableCell-root': {
    bgcolor: 'grey.200',
    fontWeight: 600,
    cursor: 'pointer',
    userSelect: 'none',
    '&:hover': { bgcolor: 'grey.300' },
  },
  '& .MuiTableBody .MuiTableRow-root:hover': {
    bgcolor: 'action.hover',
  },
}

export function SavedChunksPage() {
  const [items, setItems] = useState<SavedChunkSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [sortKey, setSortKey] = useState<SortKey>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null)

  const [selected, setSelected] = useState<SavedChunkDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailSuccess, setDetailSuccess] = useState<string | null>(null)
  const [savingDetail, setSavingDetail] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const loadList = async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetch('/api/ner/chunks')
      const data = (await r.json()) as { items?: SavedChunkSummary[]; error?: string }
      if (!r.ok) throw new Error(data?.error || `Request failed (${r.status})`)
      setItems(data.items ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadList()
  }, [])

  const handleSort = (key: SortKey) => {
    if (!key) return
    setSortDir((prev) => (sortKey === key && prev === 'asc' ? 'desc' : 'asc'))
    setSortKey(key)
  }

  const sortedItems = (() => {
    if (!sortKey) return items
    const dir = sortDir === 'asc' ? 1 : -1
    return [...items].sort((a, b) => {
      const va = a[sortKey as keyof SavedChunkSummary]
      const vb = b[sortKey as keyof SavedChunkSummary]
      const na = typeof va === 'number' ? va : (va ?? '').toString()
      const nb = typeof vb === 'number' ? vb : (vb ?? '').toString()
      return dir * (na < nb ? -1 : na > nb ? 1 : 0)
    })
  })()

  const openDetail = async (id: number) => {
    setDetailError(null)
    setDetailSuccess(null)
    try {
      const r = await fetch(`/api/ner/chunks/${id}`)
      const data = (await r.json()) as SavedChunkDetail & { error?: string }
      if (!r.ok) throw new Error(data?.error || `Request failed (${r.status})`)
      if (!Array.isArray(data.entities)) {
        data.entities = []
      }
      setSelected(data)
      setSelectedRowId(id)
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : String(e))
    }
  }

  const toggleStar = async (chunk: SavedChunkSummary) => {
    const id = chunk.id
    const next = !(chunk.is_starred === 1 || chunk.is_starred === true)
    try {
      await fetch(`/api/ner/chunks/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_starred: next }),
      })
      setItems((prev) =>
        prev.map((c) => (c.id === id ? { ...c, is_starred: next ? 1 : 0 } : c)),
      )
      if (selected?.id === id) {
        setSelected({ ...selected, is_starred: next ? 1 : 0 })
      }
    } catch {
      // ignore for now
    }
  }

  const deleteChunk = async (id: number) => {
    if (!window.confirm('Delete this chunk and its entities?')) return
    setDeletingId(id)
    try {
      await fetch(`/api/ner/chunks/${id}`, { method: 'DELETE' })
      setItems((prev) => prev.filter((c) => c.id !== id))
      if (selected?.id === id) setSelected(null)
    } catch {
      // ignore for now
    } finally {
      setDeletingId(null)
    }
  }

  const saveDetail = async () => {
    if (!selected) return
    setSavingDetail(true)
    setDetailError(null)
    setDetailSuccess(null)
    try {
      await fetch(`/api/ner/chunks/${selected.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_title: selected.doc_title,
          corrected_text: selected.corrected_text,
          status: selected.status,
        }),
      })
      setItems((prev) =>
        prev.map((c) =>
          c.id === selected.id
            ? {
                ...c,
                doc_title: selected.doc_title,
                status: selected.status,
              }
            : c,
        ),
      )
      setDetailSuccess('Saved chunk changes.')
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingDetail(false)
    }
  }

  const updateEntityField = (entityId: number, field: keyof SavedEntity, value: any) => {
    if (!selected) return
    setSelected({
      ...selected,
      entities: selected.entities.map((e) =>
        e.id === entityId ? { ...e, [field]: value } : e,
      ),
    })
  }

  const saveEntity = async (entity: SavedEntity) => {
    try {
      await fetch(`/api/ner/entities/${entity.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          label: entity.label,
          text: entity.text,
          score: entity.score,
          start: entity.start,
          end: entity.end,
        }),
      })
    } catch {
      // ignore for now
    }
  }

  const deleteEntityLocal = async (entityId: number) => {
    if (!selected) return
    try {
      await fetch(`/api/ner/entities/${entityId}`, { method: 'DELETE' })
      setSelected({
        ...selected,
        entities: selected.entities.filter((e) => e.id !== entityId),
      })
    } catch {
      // ignore
    }
  }

  const addEntityLocal = async () => {
    if (!selected) return
    try {
      const r = await fetch(`/api/ner/chunks/${selected.id}/entities`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          label: 'LABEL',
          text: 'New entity',
        }),
      })
      const data = (await r.json()) as { id?: number }
      const newId = data.id ?? Math.max(0, ...selected.entities.map((e) => e.id)) + 1
      setSelected({
        ...selected,
        entities: [
          ...selected.entities,
          { id: newId, label: 'LABEL', text: 'New entity', score: undefined, start: null, end: null },
        ],
      })
    } catch {
      // ignore
    }
  }

  return (
    <Box sx={{ width: '100%', minWidth: 0 }}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}
          <TableContainer sx={{ maxHeight: '70vh', overflow: 'auto' }}>
            <Table size="small" stickyHeader sx={EXCEL_GRID}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 40, textAlign: 'center' }}>#</TableCell>
                  <TableCell sx={{ width: 48, textAlign: 'center' }}>★</TableCell>
                  <TableCell onClick={() => handleSort('id')} sx={{ width: 60 }}>
                    ID {sortKey === 'id' && (sortDir === 'asc' ? <ArrowUpwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} /> : <ArrowDownwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} />)}
                  </TableCell>
                  <TableCell onClick={() => handleSort('doc_title')} sx={{ minWidth: 140 }}>
                    Title {sortKey === 'doc_title' && (sortDir === 'asc' ? <ArrowUpwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} /> : <ArrowDownwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} />)}
                  </TableCell>
                  <TableCell sx={{ minWidth: 90 }}>Model</TableCell>
                  <TableCell onClick={() => handleSort('chunk_index')} sx={{ width: 80, textAlign: 'center' }}>
                    Chunk # {sortKey === 'chunk_index' && (sortDir === 'asc' ? <ArrowUpwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} /> : <ArrowDownwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} />)}
                  </TableCell>
                  <TableCell onClick={() => handleSort('start')} sx={{ width: 90 }}>
                    Span {sortKey === 'start' && (sortDir === 'asc' ? <ArrowUpwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} /> : <ArrowDownwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} />)}
                  </TableCell>
                  <TableCell sx={{ minWidth: 200 }}>Chunk text</TableCell>
                  <TableCell sx={{ width: 80 }}>Status</TableCell>
                  <TableCell onClick={() => handleSort('created_at')} sx={{ width: 140 }}>
                    Created {sortKey === 'created_at' && (sortDir === 'asc' ? <ArrowUpwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} /> : <ArrowDownwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} />)}
                  </TableCell>
                  <TableCell sx={{ width: 88, borderRight: 'none' }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedItems.map((c, idx) => (
                  <TableRow
                    key={c.id}
                    hover
                    onClick={() => openDetail(c.id)}
                    selected={selectedRowId === c.id}
                    sx={{
                      cursor: 'pointer',
                      bgcolor: selectedRowId === c.id ? 'action.selected' : undefined,
                      '&.Mui-selected': { bgcolor: 'action.selected' },
                      '&.Mui-selected:hover': { bgcolor: 'action.selected' },
                    }}
                  >
                    <TableCell sx={{ textAlign: 'center', color: 'text.secondary' }}>{idx + 1}</TableCell>
                    <TableCell onClick={(ev) => ev.stopPropagation()} sx={{ textAlign: 'center' }}>
                      <IconButton
                        size="small"
                        onClick={() => toggleStar(c)}
                        aria-label="star"
                      >
                        {c.is_starred === 1 || c.is_starred === true ? (
                          <StarIcon fontSize="small" color="warning" />
                        ) : (
                          <StarBorderOutlinedIcon fontSize="small" />
                        )}
                      </IconButton>
                    </TableCell>
                    <TableCell>{c.id}</TableCell>
                    <TableCell sx={{ maxWidth: 180 }}>
                      <Typography variant="body2" noWrap title={c.doc_title ?? ''}>
                        {c.doc_title || '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>{c.model ?? '—'}</TableCell>
                    <TableCell sx={{ textAlign: 'center' }}>{(c.chunk_index ?? 0) + 1}</TableCell>
                    <TableCell>{`${c.start ?? 0}–${c.end ?? 0}`}</TableCell>
                    <TableCell sx={{ maxWidth: 400, whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5 }}>
                      <Typography variant="body2" component="span" sx={{ fontSize: 12 }}>
                        {c.corrected_text || '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>{c.status || '—'}</TableCell>
                    <TableCell>{formatCreated(c.created_at)}</TableCell>
                    <TableCell onClick={(ev) => ev.stopPropagation()} sx={{ borderRight: 'none' }}>
                      <Stack direction="row" spacing={0.25}>
                        <Tooltip title="View / edit">
                          <IconButton
                            size="small"
                            onClick={() => openDetail(c.id)}
                            aria-label="edit"
                          >
                            <EditOutlinedIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete">
                          <IconButton
                            size="small"
                            onClick={() => deleteChunk(c.id)}
                            aria-label="delete"
                            disabled={deletingId === c.id}
                          >
                            <DeleteOutlineOutlinedIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
                {!loading && items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={10} sx={{ opacity: 0.7 }}>
                      No saved chunks yet. Run NER with chunking enabled, then click
                      &quot;Save chunks to database&quot; on the Extracting NER page.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      </Paper>

      <Dialog
        open={!!selected}
        onClose={() => setSelected(null)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>Chunk detail</DialogTitle>
        <DialogContent dividers>
          {detailError && <Alert severity="error">{detailError}</Alert>}
          {detailSuccess && <Alert severity="success">{detailSuccess}</Alert>}
          {selected && (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                label="Title"
                value={selected.doc_title ?? ''}
                onChange={(e) =>
                  setSelected({ ...selected, doc_title: e.target.value })
                }
                fullWidth
                size="small"
              />
              <Stack direction="row" spacing={1}>
                <TextField
                  label="Status"
                  value={selected.status ?? ''}
                  onChange={(e) =>
                    setSelected({ ...selected, status: e.target.value })
                  }
                  size="small"
                />
                <Chip
                  size="small"
                  label={selected.model ?? ''}
                  variant="outlined"
                  sx={{ alignSelf: 'center' }}
                />
                <Chip
                  size="small"
                  label={`Chunk ${(selected.chunk_index ?? 0) + 1}`}
                  variant="outlined"
                  sx={{ alignSelf: 'center' }}
                />
              </Stack>
              <Box>
                <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.8 }}>
                  Corrected text
                </Typography>
                <TextField
                  value={selected.corrected_text ?? ''}
                  onChange={(e) =>
                    setSelected({ ...selected, corrected_text: e.target.value })
                  }
                  fullWidth
                  multiline
                  minRows={4}
                  sx={{ mt: 0.5 }}
                />
                {selected.corrected_text && (
                  <Box
                    sx={{
                      mt: 1,
                      p: 1,
                      borderRadius: 1,
                      border: '1px solid',
                      borderColor: 'divider',
                      bgcolor: 'grey.50',
                      maxHeight: 200,
                      overflow: 'auto',
                    }}
                  >
                    <Typography
                      component="span"
                      sx={{
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        lineHeight: 1.7,
                      }}
                    >
                      {buildHighlightSegments(
                        selected.corrected_text ?? '',
                        selected.entities.map(
                          (e) =>
                            ({
                              text: e.text,
                              label: e.label,
                              start: e.start ?? undefined,
                              end: e.end ?? undefined,
                            } as NerEntity),
                        ),
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
                        ),
                      )}
                    </Typography>
                  </Box>
                )}
              </Box>

              <Box>
                <Stack
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  sx={{ mb: 1 }}
                >
                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                    Entities ({selected.entities.length})
                  </Typography>
                  <Button size="small" variant="outlined" onClick={addEntityLocal}>
                    + Add row
                  </Button>
                </Stack>
                {selected.entities.length > 0 ? (
                <TableContainer sx={{ maxHeight: 280, overflow: 'auto' }}>
                  <Table size="small" sx={EXCEL_GRID}>
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ width: 36, textAlign: 'center' }}>#</TableCell>
                        <TableCell sx={{ minWidth: 100 }}>Label</TableCell>
                        <TableCell sx={{ minWidth: 160 }}>Text</TableCell>
                        <TableCell sx={{ width: 70, textAlign: 'right' }}>Score</TableCell>
                        <TableCell sx={{ width: 60, textAlign: 'right' }}>Start</TableCell>
                        <TableCell sx={{ width: 60, textAlign: 'right' }}>End</TableCell>
                        <TableCell sx={{ width: 90, borderRight: 'none' }}>Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {selected.entities.map((e, idx) => (
                        <TableRow key={e.id} hover>
                          <TableCell sx={{ textAlign: 'center', color: 'text.secondary' }}>
                            {idx + 1}
                          </TableCell>
                          <TableCell sx={{ p: 0 }}>
                            <InputBase
                              value={e.label}
                              onChange={(ev) =>
                                updateEntityField(e.id, 'label', ev.target.value)
                              }
                              size="small"
                              fullWidth
                              sx={{ px: 1, py: 0.5, fontSize: 13 }}
                            />
                          </TableCell>
                          <TableCell sx={{ p: 0 }}>
                            <InputBase
                              value={e.text}
                              onChange={(ev) =>
                                updateEntityField(e.id, 'text', ev.target.value)
                              }
                              size="small"
                              fullWidth
                              sx={{ px: 1, py: 0.5, fontSize: 13 }}
                            />
                          </TableCell>
                          <TableCell sx={{ p: 0 }}>
                            <InputBase
                              value={e.score ?? ''}
                              onChange={(ev) =>
                                updateEntityField(
                                  e.id,
                                  'score',
                                  ev.target.value ? Number(ev.target.value) : undefined,
                                )
                              }
                              size="small"
                              type="number"
                              inputProps={{ step: 0.01 }}
                              sx={{ px: 1, py: 0.5, fontSize: 13, textAlign: 'right', width: '100%' }}
                            />
                          </TableCell>
                          <TableCell sx={{ p: 0 }}>
                            <InputBase
                              value={e.start ?? ''}
                              onChange={(ev) =>
                                updateEntityField(
                                  e.id,
                                  'start',
                                  ev.target.value ? Number(ev.target.value) : undefined,
                                )
                              }
                              size="small"
                              type="number"
                              sx={{ px: 1, py: 0.5, fontSize: 13, textAlign: 'right', width: '100%' }}
                            />
                          </TableCell>
                          <TableCell sx={{ p: 0 }}>
                            <InputBase
                              value={e.end ?? ''}
                              onChange={(ev) =>
                                updateEntityField(
                                  e.id,
                                  'end',
                                  ev.target.value ? Number(ev.target.value) : undefined,
                                )
                              }
                              size="small"
                              type="number"
                              sx={{ px: 1, py: 0.5, fontSize: 13, textAlign: 'right', width: '100%' }}
                            />
                          </TableCell>
                          <TableCell sx={{ borderRight: 'none' }}>
                            <Stack direction="row" spacing={0.25}>
                              <Button size="small" sx={{ minWidth: 0, px: 0.75 }} onClick={() => saveEntity(e)}>
                                Save
                              </Button>
                              <IconButton size="small" onClick={() => deleteEntityLocal(e.id)} aria-label="delete">
                                <DeleteOutlineOutlinedIcon fontSize="small" />
                              </IconButton>
                            </Stack>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                ) : (
                  <Typography variant="body2" sx={{ py: 2, opacity: 0.6, textAlign: 'center' }}>
                    No entities. Click &quot;+ Add row&quot; to add.
                  </Typography>
                )}
              </Box>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelected(null)}>Close</Button>
          <Button
            onClick={saveDetail}
            variant="contained"
            disabled={savingDetail || !selected}
          >
            {savingDetail ? 'Saving…' : 'Save changes'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

