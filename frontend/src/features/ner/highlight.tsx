import { Box, Chip, Stack, Typography } from '@mui/material'
import type { NerEntity } from '../../types/ner'

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
}) {
  const { text, entities, title = 'Highlighted text' } = props
  const segments = buildHighlightSegments(text, entities)
  const labelsInResult = Array.from(new Set(entities.map((e) => e.label)))

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
    </Stack>
  )
}

