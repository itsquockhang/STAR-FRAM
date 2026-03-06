import { Box, Paper, Typography } from '@mui/material'

export function PlaceholderPage(props: { title: string; description?: string }) {
  return (
    <Box sx={{ maxWidth: 900 }}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
          {props.title}
        </Typography>
        <Typography variant="body2" sx={{ opacity: 0.8 }}>
          {props.description ?? 'Coming soon.'}
        </Typography>
      </Paper>
    </Box>
  )
}

