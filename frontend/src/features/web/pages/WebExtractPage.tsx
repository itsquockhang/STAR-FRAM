import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Box, Button, CircularProgress, Paper, Stack, TextField, Typography } from '@mui/material'
import { useNerStore } from '../../../state/nerStore'

type WebExtractResponse = {
  text?: string
  url?: string
  char_count?: number
  error?: string
}

export function WebExtractPage() {
  const navigate = useNavigate()
  const { actions } = useNerStore()
  const DEFAULT_URL =
    'https://wikifarmer.com/library/vi/article/kiem-soat-co-dai-trong-canh-tac-lua-mi'
  const [url, setUrl] = useState(DEFAULT_URL)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<WebExtractResponse | null>(null)

  const onFetch = useCallback(async () => {
    const trimmed = url.trim()
    if (!trimmed) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const r = await fetch('/api/web/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmed }),
      })
      const data = (await r.json()) as WebExtractResponse
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
  }, [url])

  const onUseInNer = useCallback(() => {
    if (!result?.text) return
    actions.setText(result.text)
    navigate('/extracting-ner')
  }, [actions, navigate, result?.text])

  const onSaveTxt = useCallback(() => {
    if (!result?.text) return
    const blob = new Blob([result.text], { type: 'text/plain;charset=utf-8' })
    // Try to derive a simple filename from URL host/path, fallback to generic
    let filename = 'web-extract.txt'
    try {
      if (result.url) {
        const u = new URL(result.url)
        const hostPart = u.hostname.replace(/^www\./, '').replace(/[^a-zA-Z0-9.-]+/g, '-')
        const pathPart = u.pathname
          .split('/')
          .filter(Boolean)
          .slice(-2)
          .join('-')
          .replace(/[^a-zA-Z0-9.-]+/g, '-')
        const base = [hostPart, pathPart].filter(Boolean).join('__')
        if (base) filename = `${base}.txt`
      }
    } catch {
      // ignore URL parsing errors and keep default filename
    }
    const urlObj = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = urlObj
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(urlObj)
  }, [result?.text, result?.url])

  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch">
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Extract text from URL
            </Typography>

            <TextField
              label="Web URL"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://..."
              fullWidth
              helperText="Paste a public URL. We'll extract main text using Trafilatura."
            />

            {error && <Alert severity="error">{error}</Alert>}

            <Button variant="contained" onClick={onFetch} disabled={loading || !url.trim()}>
              {loading ? (
                <Stack direction="row" alignItems="center" gap={1}>
                  <CircularProgress size={18} />
                  <span>Extracting…</span>
                </Stack>
              ) : (
                'Extract'
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

                {(result.url || result.char_count != null) && (
                  <Typography variant="caption" sx={{ opacity: 0.75 }}>
                    {result.url && `URL: ${result.url}`}
                    {result.char_count != null && ` · ${result.char_count} chars`}
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
                No text yet. Paste a URL and click "Extract".
              </Typography>
            )}
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}

