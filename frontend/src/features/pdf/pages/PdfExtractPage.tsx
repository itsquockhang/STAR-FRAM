import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { useNerStore } from '../../../state/nerStore'

type PdfExtractResponse = {
  text?: string
  filename?: string
  byte_size?: number
  method?: string
  page_count?: number
  error?: string
}

export function PdfExtractPage() {
  const navigate = useNavigate()
  const { actions } = useNerStore()
  const [file, setFile] = useState<File | null>(null)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<PdfExtractResponse | null>(null)

  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl)
    }
  }, [pdfUrl])

  const onFileChange = useCallback((f: File | null) => {
    if (pdfUrl) {
      URL.revokeObjectURL(pdfUrl)
      setPdfUrl(null)
    }
    setFile(f)
    setResult(null)
    setError(null)
    if (f) setPdfUrl(URL.createObjectURL(f))
  }, [pdfUrl])

  const onExtract = useCallback(async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const r = await fetch('/api/pdf/extract', { method: 'POST', body: form })
      const data = (await r.json()) as PdfExtractResponse
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

  const onSaveTxt = useCallback(() => {
    if (!result?.text) return
    const blob = new Blob([result.text], { type: 'text/plain;charset=utf-8' })
    const name = result.filename ? result.filename.replace(/\.pdf$/i, '') + '.txt' : 'pdf-extract.txt'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [result?.text, result?.filename])

  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch" sx={{ width: '100%' }}>
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Paper variant="outlined" sx={{ p: 2, flex: 1, display: 'flex', flexDirection: 'column', minHeight: 420 }}>
          <Stack spacing={2} sx={{ flex: 1, minHeight: 0 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              PDF
            </Typography>
            <Button variant="outlined" component="label" disabled={loading}>
              Choose PDF file
              <input
                type="file"
                hidden
                accept=".pdf,application/pdf"
                onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
              />
            </Button>
            {file && (
              <Typography variant="caption" sx={{ opacity: 0.75 }}>
                {file.name} ({Math.round(file.size / 1024)} KB)
              </Typography>
            )}
            {error && <Alert severity="error">{error}</Alert>}
            {file && (
              <Button variant="contained" onClick={onExtract} disabled={loading}>
                {loading ? (
                  <Stack direction="row" alignItems="center" gap={1}>
                    <CircularProgress size={18} />
                    <span>Extracting…</span>
                  </Stack>
                ) : (
                  'Extract text'
                )}
              </Button>
            )}
            {pdfUrl && file && (
              <Box
                sx={{
                  flex: 1,
                  minHeight: 280,
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 1,
                  overflow: 'hidden',
                  bgcolor: 'grey.100',
                }}
              >
                <embed
                  src={pdfUrl}
                  type="application/pdf"
                  style={{ width: '100%', height: '100%', minHeight: 360 }}
                  title="PDF preview"
                />
              </Box>
            )}
            {!file && (
              <Typography variant="body2" sx={{ opacity: 0.6, flex: 1 }}>
                Choose a PDF to preview and extract text.
              </Typography>
            )}
          </Stack>
        </Paper>
      </Box>

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 2, height: '100%', minHeight: 420 }}>
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
                {(result.filename || result.method) && (
                  <Typography variant="caption" sx={{ opacity: 0.75 }}>
                    {result.filename}
                    {result.method && ` · ${result.method}`}
                    {result.page_count != null && ` · ${result.page_count} pages`}
                    {result.byte_size != null && ` · ${Math.round(result.byte_size / 1024)} KB`}
                  </Typography>
                )}
                <Stack direction="row" spacing={1}>
                  <Button variant="outlined" onClick={onUseInNer} disabled={!result.text}>
                    Use in NER
                  </Button>
                  <Button variant="text" onClick={onSaveTxt} disabled={!result.text}>
                    Save as .txt
                  </Button>
                </Stack>
              </>
            ) : (
              <Typography variant="body2" sx={{ opacity: 0.7 }}>
                No text yet. Select a PDF on the left and click &quot;Extract text&quot;.
              </Typography>
            )}
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}
