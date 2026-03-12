import { Box, Container } from '@mui/material'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Navbar } from './components/Navbar'
import { ExtractingNerPage } from './features/ner/pages/ExtractingNerPage'
import { DocumentImportPage } from './features/docs/pages/DocumentImportPage'
import { YouTubeTranscriptPage } from './features/youtube/pages/YouTubeTranscriptPage'
import { WebExtractPage } from './features/web/pages/WebExtractPage'

export default function App() {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        bgcolor: 'background.default',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Navbar />
      <Container maxWidth="lg" sx={{ py: 3, pb: 6, flex: 1, width: '100%' }}>
        <Routes>
          <Route path="/" element={<Navigate to="/extracting-ner" replace />} />
          <Route path="/extracting-ner" element={<ExtractingNerPage />} />
          <Route path="/youtube-transcript" element={<YouTubeTranscriptPage />} />
          <Route path="/web-extract" element={<WebExtractPage />} />
          <Route path="/document-import" element={<DocumentImportPage />} />
          {/* <Route
            path="/workspace"
            element={
              <PlaceholderPage
                title="Workspace"
                description="A place to manage shared data across features."
              />
            }
          /> */}
          <Route path="*" element={<Navigate to="/extracting-ner" replace />} />
        </Routes>
      </Container>
      <Box
        component="footer"
        sx={{
          py: 1.5,
          px: 2,
          borderTop: '1px solid',
          borderColor: 'divider',
          bgcolor: 'background.paper',
          textAlign: 'center',
          mt: 'auto',
        }}
      >
        <Box component="span" sx={{ fontSize: 12, opacity: 0.8 }}>
          STARFRAM is a research project carried out by the Faculty of Computer Science, College of Information Technology and Communication, Can Tho University, and CIRAD (France) in 2026.
        </Box>
      </Box>
    </Box>
  )
}

