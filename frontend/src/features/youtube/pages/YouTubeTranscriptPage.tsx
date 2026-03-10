import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  FormControl,
  FormControlLabel,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useNerStore } from '../../../state/nerStore'

type TranscriptResponse = {
  text?: string
  video_id?: string
  language?: string
  snippet_count?: number
  error?: string
}

export function YouTubeTranscriptPage() {
  const navigate = useNavigate()
  const { actions } = useNerStore()
  const DEFAULT_URL = 'https://www.youtube.com/watch?v=RcX_GuQnB6s'
  const [url, setUrl] = useState(DEFAULT_URL)
  const [language, setLanguage] = useState<'vi' | 'en'>('vi')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<TranscriptResponse | null>(null)

  const onFetch = useCallback(async () => {
    const trimmed = url.trim()
    if (!trimmed) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const r = await fetch('/api/youtube/transcript', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: trimmed,
          languages: language === 'vi' ? ['vi', 'en'] : ['en', 'vi'],
        }),
      })
      const data = (await r.json()) as TranscriptResponse
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
  }, [url, language])

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
              YouTube Transcript
            </Typography>
            <TextField
              label="YouTube URL or video ID"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              fullWidth
              helperText="Paste a YouTube video URL or 11-character video ID."
            />
            <FormControl>
              <Typography variant="caption" sx={{ mb: 0.5, opacity: 0.8 }}>
                Transcript language (preferred)
              </Typography>
              <RadioGroup
                row
                value={language}
                onChange={(_, v) => setLanguage(v as 'vi' | 'en')}
              >
                <FormControlLabel value="vi" control={<Radio size="small" />} label="Tiếng Việt" />
                <FormControlLabel value="en" control={<Radio size="small" />} label="English" />
              </RadioGroup>
            </FormControl>
            {error && <Alert severity="error">{error}</Alert>}
            <Button
              variant="contained"
              onClick={onFetch}
              disabled={loading || !url.trim()}
            >
              {loading ? (
                <Stack direction="row" alignItems="center" gap={1}>
                  <CircularProgress size={18} />
                  <span>Fetching…</span>
                </Stack>
              ) : (
                'Fetch transcript'
              )}
            </Button>
          </Stack>
        </Paper>
      </Box>

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Transcript
            </Typography>
            {result?.error && (
              <Alert severity="warning">
                {result.error}
                {result.video_id && (
                  <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                    Video ID: {result.video_id}
                  </Typography>
                )}
              </Alert>
            )}
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
                {(result.video_id || result.language) && (
                  <Typography variant="caption" sx={{ opacity: 0.75 }}>
                    Video ID: {result.video_id}
                    {result.language && ` · Language: ${result.language}`}
                    {result.snippet_count != null && ` · ${result.snippet_count} snippets`}
                  </Typography>
                )}
                <Button
                  variant="outlined"
                  onClick={onUseInNer}
                  disabled={!result.text}
                >
                  Use in NER
                </Button>
              </>
            ) : (
              <Typography variant="body2" sx={{ opacity: 0.7 }}>
                No transcript yet. Enter a YouTube URL and click "Fetch transcript".
              </Typography>
            )}
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}
