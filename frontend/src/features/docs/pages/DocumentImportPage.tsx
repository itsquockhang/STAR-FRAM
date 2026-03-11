import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Box, Button, CircularProgress, Paper, Stack, Typography } from '@mui/material'
import { useNerStore } from '../../../state/nerStore'

type DocExtractResponse = {
  text?: string
  filename?: string
  file_type?: string
  byte_size?: number
  error?: string
}

export function DocumentImportPage() {
  const navigate = useNavigate()
  const { actions } = useNerStore()
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<DocExtractResponse | null>(null)

  const accept = useMemo(() => ['.txt', '.docx', '.doc'].join(','), [])

  const onUpload = useCallback(async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const form = new FormData()
      form.append('file', file)

      const r = await fetch('/api/doc/extract', { method: 'POST', body: form })
      const data = (await r.json()) as DocExtractResponse
      if (!r.ok) {
        setError(data?.error ?? `Request failed (${r.status})`)
        setResult(data)
        return
      }
      setResult(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [file])

  const onUseInNer = useCallback(() => {
    if (!result?.text) return
    actions.setText(result.text)
    navigate('/extracting-ner')
  }, [actions, navigate, result?.text])

  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch">
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Import document
            </Typography>

            <Button variant="outlined" component="label" disabled={loading}>
              Choose file (.txt / .docx / .doc)
              <input
                type="file"
                hidden
                accept={accept}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Button>

            {file && (
              <Typography variant="caption" sx={{ opacity: 0.75 }}>
                Selected: {file.name} ({Math.round(file.size / 1024)} KB)
              </Typography>
            )}

            {error && <Alert severity="error">{error}</Alert>}

            <Button variant="contained" onClick={onUpload} disabled={loading || !file}>
              {loading ? (
                <Stack direction="row" alignItems="center" gap={1}>
                  <CircularProgress size={18} />
                  <span>Extracting…</span>
                </Stack>
              ) : (
                'Extract text'
              )}
            </Button>
          </Stack>
        </Paper>
      </Box>

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Extracted text
            </Typography>

            {result?.error && <Alert severity="warning">{result.error}</Alert>}

            {result?.text ? (
              <>
                <Box
                  sx={{
                    p: 1.5,
                    bgcolor: 'grey.50',
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                    maxHeight: 400,
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    lineHeight: 1.7,
                  }}
                >
                  <Typography variant="body2" component="span">
                    {result.text}
                  </Typography>
                </Box>

                {(result.filename || result.file_type) && (
                  <Typography variant="caption" sx={{ opacity: 0.75 }}>
                    File: {result.filename}
                    {result.file_type && ` · Type: ${result.file_type}`}
                    {result.byte_size != null && ` · ${result.byte_size} bytes`}
                  </Typography>
                )}

                <Button variant="outlined" onClick={onUseInNer} disabled={!result.text}>
                  Use in NER
                </Button>
              </>
            ) : (
              <Typography variant="body2" sx={{ opacity: 0.7 }}>
                No text yet. Choose a file and click "Extract text".
              </Typography>
            )}
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}

