import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  FormControl,
  IconButton,
  InputBase,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import StarBorderOutlinedIcon from '@mui/icons-material/StarBorderOutlined'
import StarIcon from '@mui/icons-material/Star'
import DeleteOutlineOutlinedIcon from '@mui/icons-material/DeleteOutlineOutlined'
import EditOutlinedIcon from '@mui/icons-material/EditOutlined'
import FilterAltOffOutlinedIcon from '@mui/icons-material/FilterAltOffOutlined'
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined'
import AddOutlinedIcon from '@mui/icons-material/AddOutlined'
import AddCircleOutlineOutlinedIcon from '@mui/icons-material/AddCircleOutlineOutlined'
import SaveOutlinedIcon from '@mui/icons-material/SaveOutlined'
import CloseOutlinedIcon from '@mui/icons-material/CloseOutlined'
import { useEffect, useMemo, useRef, useState } from 'react'
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
  classification_tags?: string[] | null
  rating?: string | null
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

const STATUS_LABELS: Record<string, string> = {
  new: 'New',
  in_progress: 'In progress',
  reviewed: 'Reviewed',
  done: 'Done',
}

const CLASSIFICATION_OPTIONS = [
  { value: 'english', label: 'English' },
  { value: 'vietnamese', label: 'Vietnamese' },
  { value: 'agriculture', label: 'Agriculture' },
  { value: 'other', label: 'Other' },
] as const

const CLASSIFICATION_LABELS: Record<string, string> = Object.fromEntries(
  CLASSIFICATION_OPTIONS.map((item) => [item.value, item.label]),
)

const RATING_OPTIONS = [
  { value: 'excellent', label: 'Excellent' },
  { value: 'good', label: 'Good' },
  { value: 'medium', label: 'Medium' },
  { value: 'needs_improvement', label: 'Needs improvement' },
] as const

const RATING_LABELS: Record<string, string> = Object.fromEntries(
  RATING_OPTIONS.map((item) => [item.value, item.label]),
)

const MANUAL_ENTITY_LABEL_DEFAULTS = [] as const

const STATUS_COLOR_BY_KEY: Record<string, { bg: string; text: string; border: string }> = {
  new: { bg: '#e0f2fe', text: '#075985', border: '#7dd3fc' },
  in_progress: { bg: '#fff7ed', text: '#9a3412', border: '#fdba74' },
  reviewed: { bg: '#ede9fe', text: '#5b21b6', border: '#c4b5fd' },
  done: { bg: '#dcfce7', text: '#166534', border: '#86efac' },
}

const RATING_COLOR_BY_KEY: Record<string, { bg: string; text: string; border: string }> = {
  excellent: { bg: '#dcfce7', text: '#166534', border: '#86efac' },
  good: { bg: '#dbeafe', text: '#1d4ed8', border: '#93c5fd' },
  medium: { bg: '#fef3c7', text: '#92400e', border: '#fcd34d' },
  needs_improvement: { bg: '#fee2e2', text: '#b91c1c', border: '#fca5a5' },
}

const TAG_COLOR_BY_KEY: Record<string, { bg: string; text: string; border: string }> = {
  english: { bg: '#dbeafe', text: '#1d4ed8', border: '#93c5fd' },
  vietnamese: { bg: '#dcfce7', text: '#15803d', border: '#86efac' },
  agriculture: { bg: '#ffedd5', text: '#c2410c', border: '#fdba74' },
  other: { bg: '#e5e7eb', text: '#374151', border: '#cbd5e1' },
}

const TAG_COLOR_FALLBACKS: Array<{ bg: string; text: string; border: string }> = [
  { bg: '#fce7f3', text: '#9d174d', border: '#f9a8d4' },
  { bg: '#ede9fe', text: '#5b21b6', border: '#c4b5fd' },
  { bg: '#dbeafe', text: '#1d4ed8', border: '#93c5fd' },
  { bg: '#dcfce7', text: '#15803d', border: '#86efac' },
  { bg: '#fef3c7', text: '#b45309', border: '#fcd34d' },
  { bg: '#fee2e2', text: '#b91c1c', border: '#fca5a5' },
]

function stableHash(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0
  }
  return hash
}

function getClassificationTagChipSx(tag: string) {
  const key = String(tag ?? '').trim().toLowerCase()
  const color =
    TAG_COLOR_BY_KEY[key] ?? TAG_COLOR_FALLBACKS[stableHash(key) % TAG_COLOR_FALLBACKS.length]
  return {
    bgcolor: color.bg,
    color: color.text,
    border: '1px solid',
    borderColor: color.border,
    fontWeight: 600,
  }
}

function splitTagTokens(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim().replace(/\s+/g, ' '))
    .filter(Boolean)
}

function normalizeClassificationTags(tags: unknown): string[] {
  if (typeof tags === 'string') {
    return Array.from(new Set(splitTagTokens(tags).map((tag) => tag.toLowerCase())))
  }
  if (!Array.isArray(tags)) return []
  return Array.from(
    new Set(
      tags
        .flatMap((item) => splitTagTokens(String(item ?? '')))
        .map((tag) => tag.toLowerCase())
        .filter(Boolean),
    ),
  )
}

function formatClassificationTag(tag: string): string {
  const key = String(tag ?? '').trim().toLowerCase()
  return CLASSIFICATION_LABELS[key] ?? tag
}

function formatRating(rating: string | null | undefined): string {
  if (!rating) return '—'
  return RATING_LABELS[rating] ?? rating
}

function getStatusChipSx(status: string | null | undefined) {
  const key = String(status ?? '').trim()
  const color = STATUS_COLOR_BY_KEY[key] ?? { bg: '#e5e7eb', text: '#374151', border: '#cbd5e1' }
  return {
    bgcolor: color.bg,
    color: color.text,
    border: '1px solid',
    borderColor: color.border,
    fontWeight: 600,
  }
}

function getRatingChipSx(rating: string | null | undefined) {
  const key = String(rating ?? '').trim()
  const color = RATING_COLOR_BY_KEY[key] ?? { bg: '#e5e7eb', text: '#374151', border: '#cbd5e1' }
  return {
    bgcolor: color.bg,
    color: color.text,
    border: '1px solid',
    borderColor: color.border,
    fontWeight: 600,
  }
}

function normalizeSearchText(value: unknown): string {
  return String(value ?? '')
    .normalize('NFKC')
    .toLowerCase()
    .trim()
}

function escapeCsv(value: unknown): string {
  const text = String(value ?? '')
  if (/[,"\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

function formatStatus(s: string | null | undefined): string {
  if (!s) return '—'
  return STATUS_LABELS[s] ?? s
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
type StarFilter = 'all' | 'starred' | 'unstarred'

type TextSelectionRange = {
  start: number
  end: number
  text: string
}

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
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [ratingFilter, setRatingFilter] = useState<string>('all')
  const [classificationFilter, setClassificationFilter] = useState<string[]>([])
  const [starFilter, setStarFilter] = useState<StarFilter>('all')
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)

  const [selected, setSelected] = useState<SavedChunkDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailSuccess, setDetailSuccess] = useState<string | null>(null)
  const [savingDetail, setSavingDetail] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [manualEntityLabel, setManualEntityLabel] = useState('')
  const [selectedTextRange, setSelectedTextRange] = useState<TextSelectionRange | null>(null)
  const [addingEntityFromSelection, setAddingEntityFromSelection] = useState(false)
  const correctedTextInputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null)

  const loadList = async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetch('/api/ner/chunks')
      const data = (await r.json()) as { items?: SavedChunkSummary[]; error?: string }
      if (!r.ok) throw new Error(data?.error || `Request failed (${r.status})`)
      setItems(
        (data.items ?? []).map((item) => ({
          ...item,
          classification_tags: normalizeClassificationTags(item.classification_tags),
          rating: item.rating ? String(item.rating) : null,
        })),
      )
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

  const resetFilters = () => {
    setSearchText('')
    setStatusFilter('all')
    setRatingFilter('all')
    setClassificationFilter([])
    setStarFilter('all')
    setPage(0)
  }

  const filteredItems = useMemo(() => {
    const query = normalizeSearchText(searchText)
    return items.filter((item) => {
      const tags = normalizeClassificationTags(item.classification_tags)
      const isStarred = item.is_starred === 1 || item.is_starred === true

      if (statusFilter !== 'all' && (item.status ?? 'new') !== statusFilter) {
        return false
      }
      if (ratingFilter !== 'all' && (item.rating ?? '') !== ratingFilter) {
        return false
      }
      if (starFilter === 'starred' && !isStarred) {
        return false
      }
      if (starFilter === 'unstarred' && isStarred) {
        return false
      }
      if (classificationFilter.length > 0 && !classificationFilter.every((tag) => tags.includes(tag))) {
        return false
      }
      if (!query) {
        return true
      }

      const haystack = [
        item.id,
        item.doc_title,
        item.model,
        item.corrected_text,
        item.status,
        item.rating,
        tags.join(' '),
      ]
        .map(normalizeSearchText)
        .join(' ')

      return haystack.includes(query)
    })
  }, [items, searchText, statusFilter, ratingFilter, starFilter, classificationFilter])

  const classificationOptions = useMemo(() => {
    const unique = new Set<string>(CLASSIFICATION_OPTIONS.map((option) => option.value))
    for (const item of items) {
      for (const tag of normalizeClassificationTags(item.classification_tags)) {
        unique.add(tag)
      }
    }
    for (const tag of classificationFilter) {
      unique.add(tag)
    }
    for (const tag of normalizeClassificationTags(selected?.classification_tags)) {
      unique.add(tag)
    }
    return Array.from(unique).sort((a, b) =>
      formatClassificationTag(a).localeCompare(formatClassificationTag(b), 'en'),
    )
  }, [classificationFilter, items, selected?.classification_tags])

  const manualEntityLabelOptions = useMemo(() => {
    const unique = new Set<string>(MANUAL_ENTITY_LABEL_DEFAULTS)
    for (const entity of selected?.entities ?? []) {
      const label = String(entity.label ?? '').trim()
      if (label) {
        unique.add(label)
      }
    }
    return Array.from(unique).sort((a, b) => a.localeCompare(b, 'en'))
  }, [selected?.entities])

  const sortedItems = useMemo(() => {
    if (!sortKey) return filteredItems
    const dir = sortDir === 'asc' ? 1 : -1
    return [...filteredItems].sort((a, b) => {
      const va = a[sortKey as keyof SavedChunkSummary]
      const vb = b[sortKey as keyof SavedChunkSummary]
      const na = typeof va === 'number' ? va : (va ?? '').toString()
      const nb = typeof vb === 'number' ? vb : (vb ?? '').toString()
      return dir * (na < nb ? -1 : na > nb ? 1 : 0)
    })
  }, [filteredItems, sortDir, sortKey])

  useEffect(() => {
    const maxPage = Math.max(0, Math.ceil(sortedItems.length / rowsPerPage) - 1)
    if (page > maxPage) {
      setPage(maxPage)
    }
  }, [page, rowsPerPage, sortedItems.length])

  const pagedItems = useMemo(() => {
    const start = page * rowsPerPage
    return sortedItems.slice(start, start + rowsPerPage)
  }, [page, rowsPerPage, sortedItems])

  const exportCsv = () => {
    const headers = [
      'id',
      'doc_title',
      'model',
      'chunk_index',
      'start',
      'end',
      'status',
      'classification_tags',
      'rating',
      'created_at',
      'updated_at',
      'corrected_text',
    ]

    const lines = [
      headers.join(','),
      ...sortedItems.map((item) =>
        [
          item.id,
          item.doc_title ?? '',
          item.model ?? '',
          item.chunk_index ?? '',
          item.start ?? '',
          item.end ?? '',
          item.status ?? '',
          normalizeClassificationTags(item.classification_tags).join('|'),
          item.rating ?? '',
          item.created_at ?? '',
          item.updated_at ?? '',
          item.corrected_text ?? '',
        ]
          .map(escapeCsv)
          .join(','),
      ),
    ]

    const csvText = lines.join('\n')
    const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-')
    const a = document.createElement('a')
    a.href = url
    a.download = `saved_chunks_${timestamp}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const updateSelectedTextRange = () => {
    if (!selected) {
      setSelectedTextRange(null)
      return
    }

    const el = correctedTextInputRef.current
    if (!el) {
      setSelectedTextRange(null)
      return
    }

    const rawStart = el.selectionStart ?? 0
    const rawEnd = el.selectionEnd ?? 0
    if (rawEnd <= rawStart) {
      setSelectedTextRange(null)
      return
    }

    const text = selected.corrected_text ?? ''
    const raw = text.slice(rawStart, rawEnd)
    if (!raw.trim()) {
      setSelectedTextRange(null)
      return
    }

    const leadingSpaces = raw.match(/^\s+/)?.[0]?.length ?? 0
    const trailingSpaces = raw.match(/\s+$/)?.[0]?.length ?? 0
    const start = rawStart + leadingSpaces
    const end = Math.max(start, rawEnd - trailingSpaces)
    const selectedText = text.slice(start, end)

    if (!selectedText.trim() || end <= start) {
      setSelectedTextRange(null)
      return
    }

    setSelectedTextRange({ start, end, text: selectedText })
  }

  const addEntityFromTextSelection = async () => {
    if (!selected || !selectedTextRange) return
    const label = manualEntityLabel.trim()
    if (!label) {
      setDetailError('Please provide an entity label before adding from selection.')
      return
    }

    setAddingEntityFromSelection(true)
    setDetailError(null)
    setDetailSuccess(null)
    try {
      const r = await fetch(`/api/ner/chunks/${selected.id}/entities`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          label,
          text: selectedTextRange.text,
          score: -1,
          start: selectedTextRange.start,
          end: selectedTextRange.end,
        }),
      })
      const data = (await r.json()) as { error?: string; id?: number }
      if (!r.ok) throw new Error(data?.error || `Request failed (${r.status})`)

      const newEntity: SavedEntity = {
        id: data.id ?? Math.max(0, ...selected.entities.map((e) => e.id)) + 1,
        label,
        text: selectedTextRange.text,
        score: -1,
        start: selectedTextRange.start,
        end: selectedTextRange.end,
      }

      setSelected((prev) => {
        if (!prev || prev.id !== selected.id) return prev
        const nextEntities = [...prev.entities, newEntity].sort((a, b) => {
          const sa = a.start ?? 0
          const sb = b.start ?? 0
          if (sa !== sb) return sa - sb
          const ea = a.end ?? 0
          const eb = b.end ?? 0
          return ea - eb
        })
        return { ...prev, entities: nextEntities }
      })

      setSelectedTextRange(null)
      setDetailSuccess('Added entity from selected text (score = -1).')
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : String(e))
    } finally {
      setAddingEntityFromSelection(false)
    }
  }

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
      setSelected({
        ...data,
        classification_tags: normalizeClassificationTags(data.classification_tags),
        rating: data.rating ? String(data.rating) : null,
      })
      setSelectedTextRange(null)
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
          classification_tags: normalizeClassificationTags(selected.classification_tags),
          rating: selected.rating ?? null,
        }),
      })
      setItems((prev) =>
        prev.map((c) =>
          c.id === selected.id
            ? {
                ...c,
                doc_title: selected.doc_title,
                status: selected.status,
                classification_tags: normalizeClassificationTags(selected.classification_tags),
                rating: selected.rating ?? null,
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
          <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
            <TextField
              size="small"
              label="Search"
              value={searchText}
              onChange={(e) => {
                setSearchText(e.target.value)
                setPage(0)
              }}
              sx={{ minWidth: 220 }}
              placeholder="Title, model, text..."
            />
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel id="saved-status-filter-label">Status</InputLabel>
              <Select
                labelId="saved-status-filter-label"
                label="Status"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(String(e.target.value))
                  setPage(0)
                }}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="new">New</MenuItem>
                <MenuItem value="in_progress">In progress</MenuItem>
                <MenuItem value="reviewed">Reviewed</MenuItem>
                <MenuItem value="done">Done</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel id="saved-rating-filter-label">Rating</InputLabel>
              <Select
                labelId="saved-rating-filter-label"
                label="Rating"
                value={ratingFilter}
                onChange={(e) => {
                  setRatingFilter(String(e.target.value))
                  setPage(0)
                }}
              >
                <MenuItem value="all">All</MenuItem>
                {RATING_OPTIONS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Autocomplete
              multiple
              freeSolo
              size="small"
              options={classificationOptions}
              value={classificationFilter}
              onChange={(_, value) => {
                setClassificationFilter(normalizeClassificationTags(value))
                setPage(0)
              }}
              filterSelectedOptions
              sx={{ minWidth: 240 }}
              renderTags={(value, getTagProps) =>
                value.map((tag, index) => (
                  <Chip
                    {...getTagProps({ index })}
                    key={tag}
                    size="small"
                    label={formatClassificationTag(tag)}
                    sx={getClassificationTagChipSx(tag)}
                  />
                ))
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Classification"
                  placeholder="Type or select tags"
                />
              )}
            />
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel id="saved-star-filter-label">Star</InputLabel>
              <Select
                labelId="saved-star-filter-label"
                label="Star"
                value={starFilter}
                onChange={(e) => {
                  setStarFilter(e.target.value as StarFilter)
                  setPage(0)
                }}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="starred">Starred</MenuItem>
                <MenuItem value="unstarred">Unstarred</MenuItem>
              </Select>
            </FormControl>
            <Stack direction="row" spacing={1}>
              <Button variant="outlined" onClick={resetFilters} startIcon={<FilterAltOffOutlinedIcon />}>
                Clear filters
              </Button>
              <Button
                variant="contained"
                onClick={exportCsv}
                disabled={sortedItems.length === 0}
                startIcon={<DownloadOutlinedIcon />}
              >
                Export CSV ({sortedItems.length})
              </Button>
            </Stack>
          </Stack>
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
                  <TableCell sx={{ minWidth: 170 }}>Classification</TableCell>
                  <TableCell sx={{ width: 130 }}>Rating</TableCell>
                  <TableCell onClick={() => handleSort('created_at')} sx={{ width: 140 }}>
                    Created {sortKey === 'created_at' && (sortDir === 'asc' ? <ArrowUpwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} /> : <ArrowDownwardIcon sx={{ fontSize: 14, verticalAlign: 'middle', ml: 0.5 }} />)}
                  </TableCell>
                  <TableCell sx={{ width: 88, borderRight: 'none' }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {pagedItems.map((c, idx) => (
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
                    <TableCell sx={{ textAlign: 'center', color: 'text.secondary' }}>
                      {page * rowsPerPage + idx + 1}
                    </TableCell>
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
                    <TableCell>
                      <Chip size="small" label={formatStatus(c.status)} sx={getStatusChipSx(c.status)} />
                    </TableCell>
                    <TableCell>
                      {normalizeClassificationTags(c.classification_tags).length > 0 ? (
                        <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: 'wrap' }}>
                          {normalizeClassificationTags(c.classification_tags).map((tag) => (
                            <Chip
                              key={`${c.id}-${tag}`}
                              size="small"
                              label={formatClassificationTag(tag)}
                              sx={getClassificationTagChipSx(tag)}
                            />
                          ))}
                        </Stack>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell>
                      {c.rating ? (
                        <Chip size="small" label={formatRating(c.rating)} sx={getRatingChipSx(c.rating)} />
                      ) : (
                        '—'
                      )}
                    </TableCell>
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
                {!loading && pagedItems.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={13} sx={{ opacity: 0.7 }}>
                      {items.length === 0
                        ? 'No saved chunks yet. Run NER with chunking enabled, then click "Save chunks to database" on the Extracting NER page.'
                        : 'No chunks match current filters.'}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={sortedItems.length}
            page={page}
            onPageChange={(_, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(Number(e.target.value))
              setPage(0)
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
        </Stack>
      </Paper>

      <Dialog
        open={!!selected}
        onClose={() => {
          setSelected(null)
          setSelectedTextRange(null)
        }}
        fullWidth
        maxWidth={false}
        PaperProps={{
          sx: {
            maxWidth: '95vw',
            width: '95vw',
            height: '90vh',
            maxHeight: '90vh',
          },
        }}
      >
        {/* <DialogTitle>Chunk detail</DialogTitle> */}
        <DialogContent dividers sx={{ overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
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
              <Stack direction="row" spacing={1} alignItems="center">
                <FormControl size="small" sx={{ minWidth: 140 }}>
                  <InputLabel id="chunk-status-label">Status</InputLabel>
                  <Select
                    labelId="chunk-status-label"
                    label="Status"
                    value={selected.status ?? 'new'}
                    onChange={(e) =>
                      setSelected({ ...selected, status: e.target.value })
                    }
                  >
                    <MenuItem value="new">New</MenuItem>
                    <MenuItem value="in_progress">In progress</MenuItem>
                    <MenuItem value="reviewed">Reviewed</MenuItem>
                    <MenuItem value="done">Done</MenuItem>
                  </Select>
                </FormControl>
                <Autocomplete
                  multiple
                  freeSolo
                  size="small"
                  options={classificationOptions}
                  value={normalizeClassificationTags(selected.classification_tags)}
                  onChange={(_, value) =>
                    setSelected({
                      ...selected,
                      classification_tags: normalizeClassificationTags(value),
                    })
                  }
                  filterSelectedOptions
                  sx={{ minWidth: 260 }}
                  renderTags={(value, getTagProps) =>
                    value.map((tag, index) => (
                      <Chip
                        {...getTagProps({ index })}
                        key={tag}
                        size="small"
                        label={formatClassificationTag(tag)}
                        sx={getClassificationTagChipSx(tag)}
                      />
                    ))
                  }
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Classification"
                      placeholder="Type new tags..."
                    />
                  )}
                />
                <FormControl size="small" sx={{ minWidth: 170 }}>
                  <InputLabel id="chunk-rating-label">Rating</InputLabel>
                  <Select
                    labelId="chunk-rating-label"
                    label="Rating"
                    value={selected.rating ?? ''}
                    onChange={(e) =>
                      setSelected({
                        ...selected,
                        rating: e.target.value ? String(e.target.value) : null,
                      })
                    }
                  >
                    <MenuItem value="">
                      <em>Not selected</em>
                    </MenuItem>
                    {RATING_OPTIONS.map((option) => (
                      <MenuItem key={option.value} value={option.value}>
                        {option.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
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
                  onChange={(e) => {
                    setSelected({ ...selected, corrected_text: e.target.value })
                    setSelectedTextRange(null)
                  }}
                  onSelect={updateSelectedTextRange}
                  onKeyUp={updateSelectedTextRange}
                  onMouseUp={updateSelectedTextRange}
                  inputRef={correctedTextInputRef}
                  fullWidth
                  multiline
                  minRows={6}
                  sx={{ mt: 0.5 }}
                />
                <Stack
                  direction={{ xs: 'column', md: 'row' }}
                  spacing={1}
                  alignItems={{ xs: 'stretch', md: 'center' }}
                  sx={{ mt: 1 }}
                >
                  <Autocomplete
                    freeSolo
                    size="small"
                    options={manualEntityLabelOptions}
                    value={manualEntityLabel}
                    onInputChange={(_, value) => setManualEntityLabel(value)}
                    onChange={(_, value) => setManualEntityLabel(typeof value === 'string' ? value : '')}
                    sx={{ minWidth: 240 }}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Manual entity label"
                        placeholder="Type label or pick suggestion"
                      />
                    )}
                  />
                  <Typography variant="body2" sx={{ opacity: 0.8 }}>
                    {selectedTextRange
                      ? `Selected range: ${selectedTextRange.start}-${selectedTextRange.end} (${selectedTextRange.text.length} chars)`
                      : 'Select text in Corrected text to create a manual entity.'}
                  </Typography>
                  <Button
                    variant="outlined"
                    onClick={addEntityFromTextSelection}
                    disabled={!selectedTextRange || addingEntityFromSelection || !manualEntityLabel.trim()}
                    startIcon={<AddCircleOutlineOutlinedIcon />}
                  >
                    {addingEntityFromSelection ? 'Adding...' : 'Add entity from selection'}
                  </Button>
                </Stack>
                {selected.corrected_text && (
                  <Box
                    sx={{
                      mt: 1,
                      p: 1,
                      borderRadius: 1,
                      border: '1px solid',
                      borderColor: 'divider',
                      bgcolor: 'grey.50',
                      maxHeight: 320,
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
                  <Button size="small" variant="outlined" onClick={addEntityLocal} startIcon={<AddOutlinedIcon />}>
                    + Add row
                  </Button>
                </Stack>
                {selected.entities.length > 0 ? (
                <TableContainer sx={{ maxHeight: 400, overflow: 'auto' }}>
                  <Table size="small" sx={EXCEL_GRID}>
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ width: 36, textAlign: 'center' }}>#</TableCell>
                        <TableCell sx={{ width: 250 }}>Label</TableCell>
                        <TableCell sx={{ minWidth: 160 }}>Text</TableCell>
                        <TableCell sx={{ width: 100, textAlign: 'right' }}>Score</TableCell>
                        <TableCell sx={{ width: 80, textAlign: 'right' }}>Start</TableCell>
                        <TableCell sx={{ width: 80, textAlign: 'right' }}>End</TableCell>
                        <TableCell sx={{ width: 100, borderRight: 'none' }}>Actions</TableCell>
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
                              <Button
                                size="small"
                                sx={{ minWidth: 0, px: 0.75 }}
                                onClick={() => saveEntity(e)}
                                startIcon={<SaveOutlinedIcon fontSize="small" />}
                              >
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
          <Button
            onClick={() => {
              setSelected(null)
              setSelectedTextRange(null)
            }}
            startIcon={<CloseOutlinedIcon />}
          >
            Close
          </Button>
          <Button
            onClick={saveDetail}
            variant="contained"
            disabled={savingDetail || !selected}
            startIcon={<SaveOutlinedIcon />}
          >
            {savingDetail ? 'Saving…' : 'Save changes'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

