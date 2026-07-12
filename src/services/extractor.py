import logging
import trafilatura

logger = logging.getLogger("starfarm.extractor")

def extract_url_content(url: str) -> dict:
    """
    Fetch and extract content from a given URL using trafilatura.
    Returns a dict with metadata and main body content (both plain text and markdown).
    """
    logger.info(f"Fetching URL: {url}")
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as e:
        logger.error(f"Error fetching URL {url}: {e}")
        raise ValueError(f"Failed to fetch the URL: {str(e)}")

    if not downloaded:
        logger.warning(f"Fetch returned empty or failed for URL: {url}")
        raise ValueError("Failed to retrieve any content from the URL. Please verify the link is accessible.")

    logger.info(f"Extracting content from {url}...")
    try:
        # Extract content in both markdown and txt formats
        markdown_text = trafilatura.extract(
            downloaded,
            output_format='markdown',
            include_links=True,
            include_images=True,
            include_tables=True,
            url=url
        )
        plain_text = trafilatura.extract(
            downloaded,
            output_format='txt',
            include_tables=True,
            url=url
        )
    except Exception as e:
        logger.error(f"Error extracting content from {url}: {e}")
        raise ValueError(f"Failed to parse content: {str(e)}")

    metadata = {}
    try:
        metadata_obj = trafilatura.extract_metadata(downloaded)
        if metadata_obj:
            metadata = metadata_obj.as_dict()
            # Clean up fields that are not JSON serializable or not needed
            metadata.pop('body', None)
            metadata.pop('commentsbody', None)
            metadata.pop('text', None)
            metadata.pop('raw_text', None)
    except Exception as e:
        logger.warning(f"Error extracting metadata from {url}: {e}")
        # Non-fatal metadata extraction error

    return {
        "url": url,
        "markdown": markdown_text or "",
        "text": plain_text or "",
        "metadata": metadata
    }
