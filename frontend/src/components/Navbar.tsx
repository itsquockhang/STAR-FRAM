import { AppBar, Box, Button, Chip, Toolbar, Typography } from '@mui/material'
import GrainOutlinedIcon from '@mui/icons-material/GrainOutlined'
import CloudDownloadOutlinedIcon from '@mui/icons-material/CloudDownloadOutlined'
import WorkspacePremiumOutlinedIcon from '@mui/icons-material/WorkspacePremiumOutlined'
import { NavLink, useLocation } from 'react-router-dom'
import { useNerStore } from '../state/nerStore'
import { Workspaces, WorkspacesOutlined } from '@mui/icons-material'

function NavButton(props: { to: string; label: string; icon?: React.ReactNode }) {
  return (
    <Button
      component={NavLink}
      to={props.to}
      sx={{
        textTransform: 'none',
        fontWeight: 500,
        px: 2,
        borderRadius: 999,
        color: 'text.secondary',
        '&.active': {
          color: 'text.primary',
          bgcolor: 'action.selected',
        },
        '&:hover': {
          bgcolor: 'action.hover',
        },
      }}
      startIcon={props.icon}
    >
      {props.label}
    </Button>
  )
}

export function Navbar() {
  const location = useLocation()
  const { state } = useNerStore()

  const badge =
    state.resp?.took_ms != null
      ? `${state.resp.took_ms} ms${state.resp.cached_labels ? ' (cached)' : ''}${
          state.resp.chunks_used != null ? ` · ${state.resp.chunks_used} chunks` : ''
        }`
      : null

  return (
    <AppBar
      position="sticky"
      color="transparent"
      elevation={0}
      sx={{
        backdropFilter: 'blur(10px)',
        backgroundColor: 'rgba(246, 247, 251, 0.9)',
        borderBottom: '1px solid',
        borderColor: 'divider',
      }}
    >
      <Toolbar sx={{ gap: 2 }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            cursor: 'pointer',
          }}
          onClick={() => {
            // Full page reload when clicking logo/title
            window.location.reload()
          }}
        >
          <Box
            component="img"
            src="/logo.png"
            alt="STARFRAM"
            sx={{ width: 48, height: 48, borderRadius: 1 }}
          />
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 800, lineHeight: 1 }}>
              STARFRAM
            </Typography>
            <Typography variant="caption" sx={{ opacity: 0.7 }}>
              Mekong agriculture insights
            </Typography>
          </Box>
        </Box>

        <Box sx={{ flex: 1 }} />

        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            bgcolor: 'background.paper',
            px: 0.75,
            py: 0.25,
            borderRadius: 999,
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          <NavButton
            to="/extracting-ner"
            label="Extracting NER"
            icon={<GrainOutlinedIcon fontSize="small" />}
          />
          <NavButton
            to="/collect-data"
            label="Collect Data"
            icon={<CloudDownloadOutlinedIcon fontSize="small" />}
          />
          <NavButton
            to="/workspace"
            label="Workspace"
            icon={<WorkspacesOutlined fontSize="small" />}
          />
        </Box>

        <Box sx={{ flex: 1 }} />

        {badge && location.pathname === '/extracting-ner' && (
          <Chip
            size="small"
            label={badge}
            sx={{
              bgcolor: 'background.paper',
              borderColor: 'divider',
            }}
            variant="outlined"
          />
        )}
        {!badge && (
          <Typography variant="caption" sx={{ opacity: 0.65 }}>
            Ready
          </Typography>
        )}
      </Toolbar>
    </AppBar>
  )
}

