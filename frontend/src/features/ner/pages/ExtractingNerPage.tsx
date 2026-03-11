import { Box, Divider, Paper, Stack, Typography } from '@mui/material'
import { useNerStore } from '../../../state/nerStore'
import { HighlightedText } from '../highlight'
import { EntitiesTable } from '../components/EntitiesTable'
import { NerForm } from '../components/NerForm'

export function ExtractingNerPage() {
  const { state, actions } = useNerStore()
  const entities = state.resp?.entities ?? []
  const chunks = state.resp?.chunks ?? []
  const textUsed = state.resp?.text_used ?? state.text

  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch">
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <NerForm
            model={state.model}
            text={state.text}
            labels={state.labels}
            threshold={state.threshold}
            chunkingMode={state.chunkingMode}
            useSpellCorrection={state.useSpellCorrection}
            multiLabel={state.multiLabel}
            loading={state.loading}
            error={state.error}
            onChangeModel={actions.setModel}
            onChangeText={actions.setText}
            onChangeLabels={actions.setLabels}
            onChangeThreshold={actions.setThreshold}
            onChangeChunkingMode={actions.setChunkingMode}
            onChangeUseSpellCorrection={actions.setUseSpellCorrection}
            onChangeMultiLabel={actions.setMultiLabel}
            onExtract={actions.extract}
            onResetExample={actions.resetExample}
          />
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
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}

