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
import {
  splitTextForTranslation,
  TRANSLATION_MAX_NEW_TOKENS,
} from '../../../utils/translationChunks'

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

type TranslateResponse = {
  translated_text?: string
  error?: string
}

type TranslationDirection = 'vi-en' | 'en-vi'

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
  const [originalTranscript, setOriginalTranscript] = useState<TranscriptResponse | null>(null)
  const [whisperLoading, setWhisperLoading] = useState(false)
  const [whisperError, setWhisperError] = useState<string | null>(null)
  const [whisperOpen, setWhisperOpen] = useState(false)
  const [translationDirection, setTranslationDirection] = useState<TranslationDirection>('vi-en')
  const [translating, setTranslating] = useState(false)
  const [translationError, setTranslationError] = useState<string | null>(null)
  const [translationProgress, setTranslationProgress] = useState<number | null>(null)

  const onFetch = useCallback(async () => {
    const trimmed = url.trim()
    if (!trimmed) return
    setLoading(true)
    setError(null)
    setTranslationError(null)
    setResult(null)
    setOriginalTranscript(null)
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
      setOriginalTranscript(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [url, language])

  const onTranslate = useCallback(async () => {
    const transcriptText = result?.text?.trim() ?? ''
    if (!transcriptText) return

    const sourceLangCode = translationDirection === 'vi-en' ? 'vi' : 'en'
    const targetLangCode = translationDirection === 'vi-en' ? 'en' : 'vi'
    const chunks = splitTextForTranslation(transcriptText)
    if (!chunks.length) return

    setTranslating(true)
    setTranslationError(null)
    setTranslationProgress(0)

    try {
      const translatedChunks: string[] = []

      for (let index = 0; index < chunks.length; index++) {
        const chunk = chunks[index]
        const r = await fetch('/api/translate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: chunk,
            source_lang_code: sourceLangCode,
            target_lang_code: targetLangCode,
            max_new_tokens: TRANSLATION_MAX_NEW_TOKENS,
          }),
        })

        const data = (await r.json()) as TranslateResponse
        if (!r.ok) throw new Error(data?.error || `Translation failed (${r.status})`)

        const translatedText = (data.translated_text ?? '').trim()
        if (!translatedText) throw new Error('Translation returned empty text.')
        translatedChunks.push(translatedText)

        const progress = Math.round(((index + 1) / chunks.length) * 100)
        setTranslationProgress(progress)
      }

      const translatedTranscript = translatedChunks.join('\n\n').trim()
      if (!translatedTranscript) throw new Error('Translation returned empty text.')

      setResult((prev) =>
        prev
          ? {
              ...prev,
              text: translatedTranscript,
              language: targetLangCode,
            }
          : prev
      )
    } catch (e) {
      setTranslationError(e instanceof Error ? e.message : String(e))
    } finally {
      setTranslating(false)
      setTranslationProgress(null)
    }
  }, [result?.text, translationDirection])

  const onUseInNer = useCallback(() => {
    if (!result?.text) return
    actions.setText(result.text)
    navigate('/extracting-ner')
  }, [actions, navigate, result?.text])

  const onRestoreOriginal = useCallback(() => {
    if (!originalTranscript) return
    setTranslationError(null)
    setResult(originalTranscript)
  }, [originalTranscript])

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

  const canUseWhisper = useMemo(
    () => !!result?.text || !!error || !!result?.error,
    [error, result?.error, result?.text]
  )

  const onRunWhisper = useCallback(async () => {
    const trimmed = url.trim()
    if (!trimmed) return
    setWhisperLoading(true)
    setWhisperError(null)
    setTranslationError(null)
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
      setOriginalTranscript({
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

  const canRestoreOriginal =
    !!originalTranscript?.text &&
    (!!result?.text || !!result?.language) &&
    (result?.text !== originalTranscript.text || result?.language !== originalTranscript.language)

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
            {translationError && <Alert severity="error">{translationError}</Alert>}
            {canUseWhisper && (
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
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                  <FormControl size="small" sx={{ minWidth: 220 }}>
                    <Select
                      value={translationDirection}
                      onChange={(e) => setTranslationDirection(e.target.value as TranslationDirection)}
                      disabled={loading || whisperLoading || translating}
                    >
                      <MenuItem value="vi-en">Vietnamese to English</MenuItem>
                      <MenuItem value="en-vi">English to Vietnamese</MenuItem>
                    </Select>
                  </FormControl>
                  <Button
                    variant="outlined"
                    onClick={onTranslate}
                    disabled={loading || whisperLoading || translating || !result.text.trim()}
                    sx={{ alignSelf: { xs: 'stretch', sm: 'center' } }}
                  >
                    {translating ? (
                      <Stack direction="row" alignItems="center" gap={1}>
                        <CircularProgress size={18} />
                        <span>
                          Translating
                          {typeof translationProgress === 'number'
                            ? `… ${translationProgress}%`
                            : '…'}
                        </span>
                      </Stack>
                    ) : (
                      'Translate'
                    )}
                  </Button>
                  <Button
                    variant="text"
                    onClick={onRestoreOriginal}
                    disabled={!canRestoreOriginal || loading || whisperLoading || translating}
                    sx={{ alignSelf: { xs: 'stretch', sm: 'center' } }}
                  >
                    Restore
                  </Button>
                </Stack>

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
                    disabled={!result.text || translating}
                  >
                    Use in NER
                  </Button>
                  <Button variant="text" onClick={onSaveTxt} disabled={!result.text || translating}>
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
