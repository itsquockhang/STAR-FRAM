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
  Typography,
} from '@mui/material'
import { useCallback, useState } from 'react'
import { useNerStore } from '../../../state/nerStore'
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
  const [translationError, setTranslationError] = useState<string | null>(null)
  const [savingChunks, setSavingChunks] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)

  const responseMatchesCurrentText = true
  const entities = responseMatchesCurrentText ? state.resp?.entities ?? [] : []
  const chunks = responseMatchesCurrentText ? state.resp?.chunks ?? [] : []
  const textUsed = responseMatchesCurrentText ? state.resp?.text_used ?? state.text : state.text

  const onTranslate = useCallback(async () => {
    const sourceLangCode = translationDirection === 'vi-en' ? 'vi' : 'en'
    const targetLangCode = translationDirection === 'vi-en' ? 'en' : 'vi'

    setTranslationError(null)
    setTranslating(true)

    try {
      const r = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: state.text,
          source_lang_code: sourceLangCode,
          target_lang_code: targetLangCode,
          max_new_tokens: 200,
        }),
      })

      const data = (await r.json()) as TranslateResponse
      if (!r.ok) throw new Error(data?.error || `Request failed (${r.status})`)

      const translatedText = (data.translated_text ?? '').trim()
      if (!translatedText) throw new Error('Translation returned empty text.')

      // Only update the editor text; user can run NER explicitly afterward.
      actions.setText(translatedText)
    } catch (e) {
      setTranslationError(e instanceof Error ? e.message : String(e))
    } finally {
      setTranslating(false)
    }
  }, [actions, state.text, translationDirection])

  const onSaveChunksToDb = useCallback(async () => {
    setSaveError(null)
    setSaveSuccess(null)

    if (!chunks.length || !textUsed.trim()) {
      setSaveError('No chunks to save. Please run NER with chunking enabled first.')
      return
    }

    setSavingChunks(true)
    try {
      const r = await fetch('/api/ner/chunks/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_title: 'NER text',
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
  }, [chunks, entities, state.labels, state.model, textUsed])

  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch">
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <InputLabel id="translation-direction-label">Translate</InputLabel>
                <Select
                  labelId="translation-direction-label"
                  value={translationDirection}
                  label="Translate"
                  onChange={(e) => setTranslationDirection(e.target.value as TranslationDirection)}
                  disabled={state.loading || translating}
                >
                  <MenuItem value="vi-en">Vietnamese to English</MenuItem>
                  <MenuItem value="en-vi">English to Vietnamese</MenuItem>
                </Select>
              </FormControl>

              <Button
                variant="outlined"
                onClick={onTranslate}
                disabled={state.loading || translating || !state.text.trim()}
              >
                {translating ? (
                  <Stack direction="row" alignItems="center" gap={1}>
                    <CircularProgress size={18} />
                    <span>Translating</span>
                  </Stack>
                ) : (
                  'Translate'
                )}
              </Button>
            </Stack>

            {translationError && <Alert severity="error">{translationError}</Alert>}

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
            <HighlightedText
              text={textUsed}
              entities={entities}
              chunks={chunks}
              showBeforeAfter={state.useSpellCorrection}
              title="Highlighted text"
            />

            <Divider />

            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Entities ({entities.length})
            </Typography>
            <EntitiesTable entities={entities} />
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}>
              <Button
                size="small"
                variant="outlined"
                onClick={onSaveChunksToDb}
                disabled={state.loading || translating || savingChunks || !chunks.length}
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
            </Box>
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}

