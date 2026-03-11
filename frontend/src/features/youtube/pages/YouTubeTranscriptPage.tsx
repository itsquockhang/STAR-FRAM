import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
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
  // WhisperX-specific fields
  source?: string
  segment_count?: number
  elapsed_seconds?: number
  model?: string
}

const WHISPERX_HF_MODELS: Record<string, string> = {
  'tiny.en': 'Systran/faster-whisper-tiny.en',
  tiny: 'Systran/faster-whisper-tiny',
  'base.en': 'Systran/faster-whisper-base.en',
  base: 'Systran/faster-whisper-base',
  'small.en': 'Systran/faster-whisper-small.en',
  small: 'Systran/faster-whisper-small',
  'medium.en': 'Systran/faster-whisper-medium.en',
  medium: 'Systran/faster-whisper-medium',
  'large-v1': 'Systran/faster-whisper-large-v1',
  'large-v2': 'Systran/faster-whisper-large-v2',
  'large-v3': 'Systran/faster-whisper-large-v3',
  large: 'Systran/faster-whisper-large-v3',
  'distil-large-v2': 'Systran/faster-distil-whisper-large-v2',
  'distil-medium.en': 'Systran/faster-distil-whisper-medium.en',
  'distil-small.en': 'Systran/faster-distil-whisper-small.en',
  'distil-large-v3': 'Systran/faster-distil-whisper-large-v3',
  'distil-large-v3.5': 'distil-whisper/distil-large-v3.5-ct2',
  'large-v3-turbo': 'mobiuslabsgmbh/faster-whisper-large-v3-turbo',
  turbo: 'mobiuslabsgmbh/faster-whisper-large-v3-turbo',
}

type WhisperModelId = keyof typeof WHISPERX_HF_MODELS

export function YouTubeTranscriptPage() {
  const navigate = useNavigate()
  const { actions } = useNerStore()
  const DEFAULT_URL = 'https://www.youtube.com/watch?v=RcX_GuQnB6s'
  const [url, setUrl] = useState(DEFAULT_URL)
  const [language, setLanguage] = useState<'vi' | 'en'>('vi')
  const [whisperModel, setWhisperModel] = useState<WhisperModelId>('tiny')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<TranscriptResponse | null>(null)
  const [whisperLoading, setWhisperLoading] = useState(false)
  const [whisperError, setWhisperError] = useState<string | null>(null)
  const [whisperOpen, setWhisperOpen] = useState(false)

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

  const onSaveTxt = useCallback(() => {
    if (!result?.text) return
    const blob = new Blob([result.text], { type: 'text/plain;charset=utf-8' })
    const filename =
      (result.video_id ? `youtube-${result.video_id}.txt` : 'youtube-transcript.txt')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [result?.text, result?.video_id])

  const canUseWhisperFallback = useMemo(
    () =>
      !!(
        (result?.error || error) &&
        (result?.error || error)?.toLowerCase().includes('no transcript available')
      ),
    [error, result?.error]
  )

  const onRunWhisper = useCallback(async () => {
    const trimmed = url.trim()
    if (!trimmed) return
    setWhisperLoading(true)
    setWhisperError(null)
    try {
      const r = await fetch('/api/youtube/whisperx', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmed, language, model: whisperModel }),
      })
      const data = (await r.json()) as TranscriptResponse
      if (!r.ok) {
        setWhisperError(data?.error ?? `WhisperX failed (${r.status})`)
        return
      }
      setResult({
        ...data,
        error: undefined,
      })
      setError(null)
      setWhisperOpen(false)
    } catch (e) {
      setWhisperError(e instanceof Error ? e.message : String(e))
    } finally {
      setWhisperLoading(false)
    }
  }, [language, url, whisperModel])

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

            <FormControl>
              <Typography variant="caption" sx={{ mb: 0.5, opacity: 0.8 }}>
                WhisperX model
              </Typography>
              <Select
                size="small"
                value={whisperModel}
                onChange={(e) => setWhisperModel(e.target.value as WhisperModelId)}
                fullWidth
              >
                {Object.keys(WHISPERX_HF_MODELS).map((id) => (
                  <MenuItem key={id} value={id}>
                    {WHISPERX_HF_MODELS[id] ?? id}
                  </MenuItem>
                ))}
              </Select>
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
            {canUseWhisperFallback && (
              <Button
                variant="outlined"
                size="small"
                onClick={() => setWhisperOpen(true)}
                sx={{ alignSelf: 'flex-start' }}
              >
                Use WhisperX (speech-to-text)
              </Button>
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
                {(result.video_id || result.language || result.source) && (
                  <Typography variant="caption" sx={{ opacity: 0.75 }}>
                    {result.video_id && <>Video ID: {result.video_id}</>}
                    {result.language && ` · Language: ${result.language}`}
                    {result.snippet_count != null && ` · ${result.snippet_count} snippets`}
                    {result.source === 'whisperx' && (
                      <>
                        {result.language || result.snippet_count != null ? ' · ' : ''}
                        WhisperX
                        {result.model && ` (${WHISPERX_HF_MODELS[result.model] ?? result.model})`}
                        {typeof result.elapsed_seconds === 'number' &&
                          ` · ${result.elapsed_seconds.toFixed(1)}s`}
                        {typeof result.segment_count === 'number' &&
                          ` · ${result.segment_count} segments`}
                      </>
                    )}
                  </Typography>
                )}
                <Stack direction="row" spacing={1}>
                  <Button
                    variant="outlined"
                    onClick={onUseInNer}
                    disabled={!result.text}
                  >
                    Use in NER
                  </Button>
                  <Button variant="text" onClick={onSaveTxt} disabled={!result.text}>
                    Save as .txt
                  </Button>
                </Stack>
              </>
            ) : (
              <Typography variant="body2" sx={{ opacity: 0.7 }}>
                No transcript yet. Enter a YouTube URL and click "Fetch transcript".
              </Typography>
            )}
          </Stack>
        </Paper>
      </Box>

      <Dialog open={whisperOpen} onClose={() => (whisperLoading ? undefined : setWhisperOpen(false))}>
        <DialogTitle>Use WhisperX to create transcript</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            <Typography variant="body2">
              This video does not have a transcript from YouTube. You can use WhisperX to automatically transcribe the audio and create a transcript.
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.7 }}>
              This may take a few minutes, especially for long videos or when running on CPU.
            </Typography>
            {whisperError && <Alert severity="error">{whisperError}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWhisperOpen(false)} disabled={whisperLoading}>
            Cancel
          </Button>
          <Button
            onClick={onRunWhisper}
            disabled={whisperLoading}
            variant="contained"
          >
            {whisperLoading ? (
              <Stack direction="row" alignItems="center" gap={1}>
                <CircularProgress size={18} />
                <span>Running WhisperX…</span>
              </Stack>
            ) : (
              'Run WhisperX'
            )}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
