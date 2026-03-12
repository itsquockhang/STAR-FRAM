import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
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
} from '@mui/material'
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

export function SavedChunksPage() {
  const [items, setItems] = useState<SavedChunkSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  const openDetail = async (id: number) => {
    setDetailError(null)
    try {
      const r = await fetch(`/api/ner/chunks/${id}`)
      const data = (await r.json()) as SavedChunkDetail & { error?: string }
      if (!r.ok) throw new Error(data?.error || `Request failed (${r.status})`)
      if (!Array.isArray(data.entities)) {
        data.entities = []
      }
      setSelected(data)
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
    <Box sx={{ maxWidth: 1200 }}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            Saved NER chunks
          </Typography>
          {error && <Alert severity="error">{error}</Alert>}
          <TableContainer sx={{ maxHeight: 420 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>Star</TableCell>
                  <TableCell>ID</TableCell>
                  <TableCell>Title</TableCell>
                  <TableCell>Model</TableCell>
                  <TableCell>Chunk #</TableCell>
                  <TableCell>Span</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((c) => (
                  <TableRow key={c.id} hover>
                    <TableCell>
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
                    <TableCell>
                      <Typography variant="body2" noWrap title={c.doc_title ?? ''}>
                        {c.doc_title || 'Untitled'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">{c.model ?? ''}</Typography>
                    </TableCell>
                    <TableCell>{(c.chunk_index ?? 0) + 1}</TableCell>
                    <TableCell>
                      <Typography variant="caption">
                        {c.start ?? 0} – {c.end ?? 0}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {c.status && (
                        <Chip
                          size="small"
                          label={c.status}
                          variant="outlined"
                          sx={{ textTransform: 'capitalize' }}
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">{c.created_at ?? ''}</Typography>
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.5}>
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
                    <TableCell colSpan={9} sx={{ opacity: 0.7 }}>
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
                  spacing={1}
                  alignItems="center"
                  justifyContent="space-between"
                >
                  <Typography
                    variant="caption"
                    sx={{ fontWeight: 700, opacity: 0.8 }}
                  >
                    Entities ({selected.entities.length})
                  </Typography>
                  <Button size="small" onClick={addEntityLocal}>
                    Add entity
                  </Button>
                </Stack>
                <Stack spacing={1} sx={{ mt: 1, maxHeight: 260, overflow: 'auto' }}>
                  {selected.entities.map((e) => (
                    <Paper
                      key={e.id}
                      variant="outlined"
                      sx={{ p: 1, display: 'flex', flexDirection: 'column', gap: 0.5 }}
                    >
                      <Stack direction="row" spacing={1} alignItems="center">
                        <TextField
                          label="Label"
                          size="small"
                          value={e.label}
                          onChange={(ev) =>
                            updateEntityField(e.id, 'label', ev.target.value)
                          }
                        />
                        <TextField
                          label="Score"
                          size="small"
                          value={e.score ?? ''}
                          onChange={(ev) =>
                            updateEntityField(
                              e.id,
                              'score',
                              ev.target.value ? Number(ev.target.value) : undefined,
                            )
                          }
                          sx={{ width: 90 }}
                        />
                        <TextField
                          label="Start"
                          size="small"
                          value={e.start ?? ''}
                          onChange={(ev) =>
                            updateEntityField(
                              e.id,
                              'start',
                              ev.target.value ? Number(ev.target.value) : undefined,
                            )
                          }
                          sx={{ width: 90 }}
                        />
                        <TextField
                          label="End"
                          size="small"
                          value={e.end ?? ''}
                          onChange={(ev) =>
                            updateEntityField(
                              e.id,
                              'end',
                              ev.target.value ? Number(ev.target.value) : undefined,
                            )
                          }
                          sx={{ width: 90 }}
                        />
                        <IconButton
                          size="small"
                          aria-label="delete-entity"
                          onClick={() => deleteEntityLocal(e.id)}
                        >
                          <DeleteOutlineOutlinedIcon fontSize="small" />
                        </IconButton>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => saveEntity(e)}
                        >
                          Save
                        </Button>
                      </Stack>
                      <TextField
                        sx={{ mt: 1 }}
                        label="Text"
                        size="small"
                        fullWidth
                        value={e.text}
                        onChange={(ev) =>
                          updateEntityField(e.id, 'text', ev.target.value)
                        }
                      />
                    </Paper>
                  ))}
                  {selected.entities.length === 0 && (
                    <Typography variant="caption" sx={{ opacity: 0.7 }}>
                      No entities saved for this chunk yet.
                    </Typography>
                  )}
                </Stack>
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

