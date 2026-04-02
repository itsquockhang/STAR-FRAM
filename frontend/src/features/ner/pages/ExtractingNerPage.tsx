import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import TranslateOutlinedIcon from '@mui/icons-material/TranslateOutlined'
import SaveOutlinedIcon from '@mui/icons-material/SaveOutlined'
import RestoreOutlinedIcon from '@mui/icons-material/RestoreOutlined'
import { useCallback, useState } from 'react'
import { useNerStore } from '../../../state/nerStore'
import {
  splitTextForTranslation,
  TRANSLATION_MAX_NEW_TOKENS,
} from '../../../utils/translationChunks'
import { HighlightedText } from '../highlight'
import { EntitiesTable } from '../components/EntitiesTable'
import { NerForm } from '../components/NerForm'

type TranslationDirection = 'vi-en' | 'en-vi'

type TranslateResponse = {
  translated_text?: string
  error?: string
}

export function ExtractingNerPage() {
  const { state, actions } = useNerStore()
  const [translationDirection, setTranslationDirection] = useState<TranslationDirection>('vi-en')
  const [translating, setTranslating] = useState(false)
  const [translationProgress, setTranslationProgress] = useState<number | null>(null)
  const [translationError, setTranslationError] = useState<string | null>(null)
  const [savingChunks, setSavingChunks] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)
  const [docTitle, setDocTitle] = useState('')
  const [preTranslateText, setPreTranslateText] = useState<string | null>(null)

  const responseMatchesCurrentText = true
  const entities = responseMatchesCurrentText ? state.resp?.entities ?? [] : []
  const textUsed = responseMatchesCurrentText ? state.resp?.text_used ?? state.text : state.text

  const onTranslate = useCallback(async () => {
    const sourceText = state.text.trim()
    if (!sourceText) return

    const sourceLangCode = translationDirection === 'vi-en' ? 'vi' : 'en'
    const targetLangCode = translationDirection === 'vi-en' ? 'en' : 'vi'
    const chunks = splitTextForTranslation(sourceText)
    if (!chunks.length) return

    setTranslationError(null)
    setPreTranslateText((prev) => prev ?? state.text)
    setTranslating(true)
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

        setTranslationProgress(Math.round(((index + 1) / chunks.length) * 100))
      }

      const merged = translatedChunks.join('\n\n').trim()
      if (!merged) throw new Error('Translation returned empty text.')

      actions.setText(merged)
    } catch (e) {
      setTranslationError(e instanceof Error ? e.message : String(e))
    } finally {
      setTranslating(false)
      setTranslationProgress(null)
    }
  }, [actions, state.text, translationDirection])

  const onRestoreOriginalText = useCallback(() => {
    if (!preTranslateText) return
    actions.setText(preTranslateText)
    setPreTranslateText(null)
    setTranslationError(null)
  }, [actions, preTranslateText])

  const chunks = responseMatchesCurrentText ? state.resp?.chunks ?? [] : []

  const onSaveChunksToDb = useCallback(async () => {
    setSaveError(null)
    setSaveSuccess(null)

    if (!chunks.length || !textUsed.trim()) {
      setSaveError('No chunks to save. Please run NER with chunking enabled first.')
      return
    }

    if (!docTitle.trim()) {
      setSaveError('Please enter a document title before saving chunks.')
      return
    }

    setSavingChunks(true)
    try {
      const r = await fetch('/api/ner/chunks/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_title: docTitle.trim(),
          model: state.model,
          labels: state.labels,
          text_used: textUsed,
          chunks,
          entities,
        }),
      })

      const data = (await r.json()) as { error?: string; chunk_ids?: number[] }
      if (!r.ok) throw new Error(data?.error || `Request failed (${r.status})`)
      setSaveSuccess(
        Array.isArray(data.chunk_ids)
          ? `Saved ${data.chunk_ids.length} chunks to database.`
          : 'Saved chunks to database.',
      )
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingChunks(false)
    }
  }, [chunks, docTitle, entities, state.labels, state.model, textUsed])

  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch">
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Stack
              direction="row"
              spacing={0.75}
              useFlexGap
              sx={{ flexWrap: 'wrap', alignItems: 'center' }}
            >
              <FormControl
                size="small"
                sx={{
                  minWidth: { xs: '100%', sm: 118 },
                  maxWidth: 140,
                  flexShrink: 0,
                  '& .MuiOutlinedInput-root': { fontSize: 13, minHeight: 32 },
                  '& .MuiInputLabel-root': { fontSize: 12 },
                }}
              >
                <InputLabel id="translation-direction-label">Lang</InputLabel>
                <Select
                  labelId="translation-direction-label"
                  value={translationDirection}
                  label="Lang"
                  onChange={(e) => setTranslationDirection(e.target.value as TranslationDirection)}
                  disabled={state.loading || translating}
                >
                  <MenuItem value="vi-en" dense sx={{ fontSize: 13, py: 0.5 }}>
                    VI → EN
                  </MenuItem>
                  <MenuItem value="en-vi" dense sx={{ fontSize: 13, py: 0.5 }}>
                    EN → VI
                  </MenuItem>
                </Select>
              </FormControl>

              <Button
                size="small"
                variant="outlined"
                onClick={onTranslate}
                disabled={state.loading || translating || !state.text.trim()}
                startIcon={!translating ? <TranslateOutlinedIcon /> : undefined}
                sx={{ px: 1.5, whiteSpace: 'nowrap' }}
              >
                {translating ? (
                  <Stack direction="row" alignItems="center" gap={1}>
                    <CircularProgress size={16} />
                    <span>
                      Translating
                      {typeof translationProgress === 'number' ? `… ${translationProgress}%` : '…'}
                    </span>
                  </Stack>
                ) : (
                  'Translate'
                )}
              </Button>

              <Button
                size="small"
                variant="outlined"
                color="inherit"
                onClick={onRestoreOriginalText}
                disabled={state.loading || translating || !preTranslateText}
                startIcon={<RestoreOutlinedIcon />}
                sx={{ px: 1.5, whiteSpace: 'nowrap' }}
              >
                Restore
              </Button>
            </Stack>

            {translationError && <Alert severity="error">{translationError}</Alert>}

            <TextField
              label="Document title"
              size="small"
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              placeholder="Enter title for saved chunks"
              disabled={state.loading || translating || savingChunks}
              fullWidth
            />

            <NerForm
              model={state.model}
              text={state.text}
              labels={state.labels}
              threshold={state.threshold}
              chunkingMode={state.chunkingMode}
              chunkCharThreshold={state.chunkCharThreshold}
              chunkSizeTokens={state.chunkSizeTokens}
              useSpellCorrection={state.useSpellCorrection}
              multiLabel={state.multiLabel}
              loading={state.loading || translating}
              error={state.error}
              onChangeModel={actions.setModel}
              onChangeText={actions.setText}
              onChangeLabels={actions.setLabels}
              onChangeThreshold={actions.setThreshold}
              onChangeChunkingMode={actions.setChunkingMode}
              onChangeChunkCharThreshold={actions.setChunkCharThreshold}
              onChangeChunkSizeTokens={actions.setChunkSizeTokens}
              onChangeUseSpellCorrection={actions.setUseSpellCorrection}
              onChangeMultiLabel={actions.setMultiLabel}
              onExtract={actions.extract}
              onResetExample={actions.resetExample}
            />

            {saveError && <Alert severity="error">{saveError}</Alert>}
            {saveSuccess && <Alert severity="success">{saveSuccess}</Alert>}
          </Stack>
        </Paper>
      </Box>

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <HighlightedText text={textUsed} entities={entities} title="Highlighted text" />

            <Divider />

            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Entities ({entities.length})
            </Typography>
            <EntitiesTable entities={entities} />
            <Stack spacing={0.5} sx={{ alignItems: 'flex-end', mt: 1 }}>
              <Button
                size="small"
                variant="outlined"
                onClick={onSaveChunksToDb}
                disabled={
                  state.loading || translating || savingChunks || !chunks.length || !docTitle.trim()
                }
                startIcon={!savingChunks ? <SaveOutlinedIcon /> : undefined}
              >
                {savingChunks ? (
                  <Stack direction="row" alignItems="center" gap={1}>
                    <CircularProgress size={16} />
                    <span>Saving chunks…</span>
                  </Stack>
                ) : (
                  'Save chunks to database'
                )}
              </Button>
              <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 360, textAlign: 'right', lineHeight: 1.35 }}>
                Saving requires a <strong>document title</strong> in the left column (above the form). Run NER with chunking enabled so chunks exist.
              </Typography>
            </Stack>
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}

