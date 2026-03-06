import { Box, Container } from '@mui/material'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Navbar } from './components/Navbar'
import { ExtractingNerPage } from './features/ner/pages/ExtractingNerPage'
import { PlaceholderPage } from './pages/PlaceholderPage'

export default function App() {
  return (
    <Box sx={{ minHeight: '100%', bgcolor: 'background.default' }}>
      <Navbar />
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Routes>
          <Route path="/" element={<Navigate to="/extracting-ner" replace />} />
          <Route path="/extracting-ner" element={<ExtractingNerPage />} />
          <Route
            path="/workspace"
            element={
              <PlaceholderPage
                title="Workspace"
                description="A place to manage shared data across features."
              />
            }
          />
          <Route path="*" element={<Navigate to="/extracting-ner" replace />} />
        </Routes>
      </Container>
    </Box>
  )
}

