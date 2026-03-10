import { Chip, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material'
import { getLabelColor } from '../highlight'
import type { NerEntity } from '../../../types/ner'

function formatScore(score: number | undefined) {
  if (typeof score !== 'number') return ''
  return score.toFixed(3)
}

export function EntitiesTable(props: { entities: NerEntity[] }) {
  const { entities } = props

  return (
    <TableContainer sx={{ maxHeight: 300 }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell>Text</TableCell>
            <TableCell>Label</TableCell>
            <TableCell>Score</TableCell>
            <TableCell>Start</TableCell>
            <TableCell>End</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {entities.map((e, idx) => (
            <TableRow key={`${e.label}-${e.start ?? 'na'}-${e.end ?? 'na'}-${idx}`}>
              <TableCell sx={{ maxWidth: 260 }}>
                <Typography variant="body2" noWrap title={e.text}>
                  {e.text}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip
                  size="small"
                  label={e.label}
                  sx={{
                    bgcolor: getLabelColor(e.label),
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                />
              </TableCell>
              <TableCell>{formatScore(e.score)}</TableCell>
              <TableCell>{e.start ?? ''}</TableCell>
              <TableCell>{e.end ?? ''}</TableCell>
            </TableRow>
          ))}
          {entities.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} sx={{ opacity: 0.75 }}>
                No entities yet. Click "Extract" to run.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

