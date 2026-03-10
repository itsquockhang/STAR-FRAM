import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControlLabel,
  FormControl,
  InputLabel,
  ListItemText,
  MenuItem,
  Select,
  Slider,
  Stack,
  TextField,
  Typography,
  Switch,
} from '@mui/material'
import type { SelectChangeEvent } from '@mui/material'
import type { SupportedModel } from '../../../types/ner'
import { SUPPORTED_MODELS } from '../../../types/ner'
import { LABEL_OPTIONS } from '../constants'

export function NerForm(props: {
  model: SupportedModel
  text: string
  labels: string[]
  threshold: number
  chunkingMode: 'none' | 'semantic' | 'token' | 'sentence'
  useSpellCorrection: boolean
  multiLabel: boolean
  loading: boolean
  error: string | null
  onChangeModel: (m: SupportedModel) => void
  onChangeText: (t: string) => void
  onChangeLabels: (labels: string[]) => void
  onChangeThreshold: (t: number) => void
  onChangeChunkingMode: (m: 'none' | 'semantic' | 'token' | 'sentence') => void
  onChangeUseSpellCorrection: (v: boolean) => void
  onChangeMultiLabel: (v: boolean) => void
  onExtract: () => void
  onResetExample: () => void
}) {
  const {
    model,
    text,
    labels,
    threshold,
    chunkingMode,
    useSpellCorrection,
    multiLabel,
    loading,
    error,
    onChangeModel,
    onChangeText,
    onChangeLabels,
    onChangeThreshold,
    onChangeChunkingMode,
    onChangeUseSpellCorrection,
    onChangeMultiLabel,
    onExtract,
    onResetExample,
  } = props

  return (
    <Stack spacing={2}>
      <FormControl fullWidth>
        <InputLabel id="model-select-label">Model</InputLabel>
        <Select
          labelId="model-select-label"
          value={model}
          label="Model"
          onChange={(e: SelectChangeEvent) => onChangeModel(e.target.value as SupportedModel)}
        >
          {SUPPORTED_MODELS.map((m) => (
            <MenuItem key={m} value={m}>
              {m}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <TextField
        label="Text"
        value={text}
        onChange={(e) => onChangeText(e.target.value)}
        minRows={5}
        maxRows={5}
        multiline
        fullWidth
      />

      <Autocomplete<string, true, false, true>
        multiple
        freeSolo
        options={LABEL_OPTIONS}
        value={labels}
        onChange={(_, value) => onChangeLabels(value)}
        filterSelectedOptions
        renderOption={(optionProps, option) => (
          <li {...optionProps} key={option}>
            <ListItemText primary={option} />
          </li>
        )}
        renderTags={(value, getTagProps) =>
          value.map((option, index) => (
            <Chip
              variant="outlined"
              size="small"
              label={option}
              {...getTagProps({ index })}
              key={`${option}-${index}`}
            />
          ))
        }
        renderInput={(params) => (
          <TextField
            {...params}
            label="Labels"
            helperText="Select from the list or type to add custom labels (multiple)."
          />
        )}
      />

      <Box>
        <Typography variant="body2" sx={{ mb: 1, opacity: 0.85 }}>
          Threshold: {threshold.toFixed(2)}
        </Typography>
        <Slider
          value={threshold}
          min={0}
          max={1}
          step={0.01}
          onChange={(_, v) => onChangeThreshold(v as number)}
        />
      </Box>

      <Box>
        <Typography variant="body2" sx={{ mb: 1, opacity: 0.85 }}>
          Chunking
        </Typography>
        <FormControl fullWidth>
          <Select
            size="small"
            value={chunkingMode}
            onChange={(e: SelectChangeEvent) =>
              onChangeChunkingMode(
                e.target.value as 'none' | 'semantic' | 'token' | 'sentence'
              )
            }
          >
            <MenuItem value="none">No chunking</MenuItem>
            <MenuItem value="semantic">Semantic chunker (Chonkie)</MenuItem>
            <MenuItem value="token">Token chunker (fixed-size tokens)</MenuItem>
            <MenuItem value="sentence">Sentence chunker (Underthesea)</MenuItem>
          </Select>
        </FormControl>
      </Box>

      <Box>
        <FormControlLabel
          control={
            <Switch
              checked={useSpellCorrection}
              onChange={(e) => onChangeUseSpellCorrection(e.target.checked)}
            />
          }
          label="Spelling correction per chunk (@protonx-legal-tc)"
        />
      </Box>

      <Box>
        <FormControlLabel
          control={
            <Switch
              checked={multiLabel}
              onChange={(e) => onChangeMultiLabel(e.target.checked)}
            />
          }
          label="Allow multiple labels per span (multi-label)"
        />
      </Box>

      {error && <Alert severity="error">{error}</Alert>}

      <Stack direction="row" spacing={1} alignItems="center">
        <Button
          variant="contained"
          onClick={onExtract}
          disabled={loading || !text.trim() || labels.length === 0}
          fullWidth
        >
          {loading ? (
            <Stack direction="row" alignItems="center" gap={1}>
              <CircularProgress size={18} />
              <span>Extracting…</span>
            </Stack>
          ) : (
            'Extract'
          )}
        </Button>
        <Button variant="outlined" onClick={onResetExample} disabled={loading}>
          Reset
        </Button>
      </Stack>
    </Stack>
  )
}

