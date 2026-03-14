import { Box, Tab, Tabs } from '@mui/material'
import OndemandVideoOutlinedIcon from '@mui/icons-material/OndemandVideoOutlined'
import LanguageOutlinedIcon from '@mui/icons-material/LanguageOutlined'
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined'
import PictureAsPdfOutlinedIcon from '@mui/icons-material/PictureAsPdfOutlined'
import { useState } from 'react'
import { YouTubeTranscriptPage } from '../../youtube/pages/YouTubeTranscriptPage'
import { WebExtractPage } from '../../web/pages/WebExtractPage'
import { DocumentImportPage } from '../../docs/pages/DocumentImportPage'
import { PdfExtractPage } from '../../pdf/pages/PdfExtractPage'

type SourceTab = 'youtube' | 'web' | 'document' | 'pdf'

const TABS: { id: SourceTab; label: string; icon: React.ReactNode }[] = [
  { id: 'youtube', label: 'YouTube Transcript', icon: <OndemandVideoOutlinedIcon fontSize="small" /> },
  { id: 'web', label: 'Web Extract', icon: <LanguageOutlinedIcon fontSize="small" /> },
  { id: 'document', label: 'Document Import', icon: <DescriptionOutlinedIcon fontSize="small" /> },
  { id: 'pdf', label: 'PDF Extract', icon: <PictureAsPdfOutlinedIcon fontSize="small" /> },
]

export function CollectDataPage() {
  const [tab, setTab] = useState<SourceTab>('youtube')

  return (
    <Box sx={{ width: '100%' }}>
      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        sx={{
          borderBottom: 1,
          borderColor: 'divider',
          mb: 2,
        }}
      >
        {TABS.map((t) => (
          <Tab
            key={t.id}
            value={t.id}
            label={t.label}
            icon={t.icon as React.ReactElement}
            iconPosition="start"
          />
        ))}
      </Tabs>
      <Box sx={{ mt: 2 }}>
        {tab === 'youtube' && <YouTubeTranscriptPage />}
        {tab === 'web' && <WebExtractPage />}
        {tab === 'document' && <DocumentImportPage />}
        {tab === 'pdf' && <PdfExtractPage />}
      </Box>
    </Box>
  )
}
