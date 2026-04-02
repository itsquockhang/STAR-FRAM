export const TRANSLATION_CHUNK_MAX_CHARS = 1200
export const TRANSLATION_MAX_NEW_TOKENS = 512

/** Split long text at newlines/spaces so each piece fits the translate API. */
export function splitTextForTranslation(text: string, maxChars = TRANSLATION_CHUNK_MAX_CHARS): string[] {
  const source = text.trim()
  if (!source) return []
  if (source.length <= maxChars) return [source]

  const chunks: string[] = []
  let remaining = source

  while (remaining.length > maxChars) {
    const minimumSplitPoint = Math.floor(maxChars * 0.6)
    let splitAt = remaining.lastIndexOf('\n', maxChars)
    if (splitAt < minimumSplitPoint) {
      splitAt = remaining.lastIndexOf(' ', maxChars)
    }
    if (splitAt < minimumSplitPoint) {
      splitAt = maxChars
    }

    const chunk = remaining.slice(0, splitAt).trim()
    if (chunk) {
      chunks.push(chunk)
    }
    remaining = remaining.slice(splitAt).trimStart()
  }

  if (remaining) {
    chunks.push(remaining)
  }

  return chunks
}
