import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  InputLabel,
  ListItemText,
  MenuItem,
  Select,
  Slider,
  Stack,
  TextField,
  Typography,
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
  loading: boolean
  error: string | null
  onChangeModel: (m: SupportedModel) => void
  onChangeText: (t: string) => void
  onChangeLabels: (labels: string[]) => void
  onChangeThreshold: (t: number) => void
  onExtract: () => void
  onResetExample: () => void
}) {
  const {
    model,
    text,
    labels,
    threshold,
    loading,
    error,
    onChangeModel,
    onChangeText,
    onChangeLabels,
    onChangeThreshold,
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
        minRows={10}
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

