"""
Zotero API client service.

Handles authentication, library access, collection listing,
item syncing, and PDF downloads from Zotero.

Based on the pyzotero library for Zotero Web API v3.
"""

from typing import List, Dict, Any, Optional, Tuple
import logging
from datetime import datetime
from pyzotero import zotero
import httpx
from pathlib import Path

logger = logging.getLogger(__name__)


class ZoteroClient:
    """
    Client for interacting with Zotero Web API v3.

    Uses pyzotero library for API communication.
    Handles item syncing, collection management, and file downloads.
    """

    def __init__(self, api_key: str, library_id: str, library_type: str = "user"):
        """
        Initialize Zotero client.

        Args:
            api_key: Zotero API key (from https://www.zotero.org/settings/keys)
            library_id: Zotero user ID or group ID
            library_type: 'user' or 'group'
        """
        self.api_key = api_key
        self.library_id = library_id
        self.library_type = library_type

        # Initialize pyzotero client
        try:
            self.zot = zotero.Zotero(
                library_id=library_id,
                library_type=library_type,
                api_key=api_key
            )
        except Exception as e:
            logger.error(f"Failed to initialize Zotero client: {e}")
            raise ValueError(f"Invalid Zotero credentials: {str(e)}")

    def test_connection(self) -> bool:
        """
        Test if the API key and library ID are valid.

        Returns:
            True if connection successful

        Raises:
            Exception with detailed error message if connection fails
        """
        try:
            masked_key = self.api_key[:8] + "..." if len(self.api_key) > 8 else "***"
            logger.info(f"Testing Zotero connection: library_type={self.library_type}, library_id={self.library_id}, api_key={masked_key}")

            num_items = self.zot.num_items()
            logger.info(f"Successfully connected to Zotero library with {num_items} items")
            return True
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Zotero connection test failed: {error_msg}")

            # Re-raise with more context
            if "403" in error_msg or "Forbidden" in error_msg:
                raise Exception("Access forbidden. Your API key may not have 'Allow library access' permission.")
            elif "401" in error_msg or "Unauthorized" in error_msg:
                raise Exception("Invalid API key. Please check your API key is correct.")
            elif "404" in error_msg or "Not Found" in error_msg:
                raise Exception("Library not found. Please check your User ID/Group ID is correct.")
            else:
                raise Exception(f"Connection failed: {error_msg}")

    def get_library_info(self) -> Dict[str, Any]:
        """
        Get basic information about the library.

        Returns:
            Dictionary with library metadata
        """
        try:
            num_items = self.zot.num_items()
            collections = self.zot.collections()
            num_collections = len(collections) if collections else 0

            return {
                "library_id": self.library_id,
                "library_type": self.library_type,
                "num_items": num_items,
                "num_collections": num_collections,
                "name": f"{self.library_type.capitalize()} Library {self.library_id}"
            }
        except Exception as e:
            logger.error(f"Failed to get library info: {e}")
            raise ValueError(f"Could not retrieve library info: {str(e)}")

    def list_collections(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List all collections in the library.

        Args:
            limit: Maximum number of collections to return

        Returns:
            List of collection dictionaries with key, name, parent, num_items
        """
        try:
            collections = self.zot.collections(limit=limit)

            result = []
            for coll in collections:
                parent_coll = coll["data"].get("parentCollection")
                # Convert False to None for proper validation
                if parent_coll is False or parent_coll == False:
                    parent_coll = None

                result.append({
                    "key": coll["key"],
                    "name": coll["data"].get("name", "Untitled Collection"),
                    "parent_collection": parent_coll,
                    "num_items": coll["meta"].get("numItems", 0)
                })

            return result
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            raise ValueError(f"Could not retrieve collections: {str(e)}")

    def get_collection_items(
        self,
        collection_key: str,
        limit: int = 100,
        start: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get all items in a specific collection.

        Args:
            collection_key: Zotero collection key
            limit: Number of items per page
            start: Starting offset for pagination

        Returns:
            Tuple of (items list, total count)
        """
        try:
            items = self.zot.collection_items(
                collection_key,
                limit=limit,
                start=start
            )
            total = self.zot.count_items()
            return self._normalize_items(items), total
        except Exception as e:
            logger.error(f"Failed to get collection items: {e}")
            raise ValueError(f"Could not retrieve collection items: {str(e)}")

    def get_all_items(
        self,
        limit: int = 100,
        start: int = 0,
        since_version: Optional[int] = None
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """
        Get all items in the library.

        Args:
            limit: Number of items per page
            start: Starting offset for pagination
            since_version: Only return items modified since this library version

        Returns:
            Tuple of (items list, total count, current library version)
        """
        try:
            params = {"limit": limit, "start": start}
            if since_version:
                params["since"] = since_version

            items = self.zot.items(**params)
            total = self.zot.num_items()
            
            # Get current library version from last response
            version = getattr(self.zot, 'last_version', None) or 0

            return self._normalize_items(items), total, version
        except Exception as e:
            logger.error(f"Failed to get items: {e}")
            raise ValueError(f"Could not retrieve items: {str(e)}")

    def get_item_pdf_url(self, item_key: str) -> Optional[str]:
        """
        Get the URL to download PDF attachment for an item.

        Args:
            item_key: Zotero item key

        Returns:
            URL string if PDF available, None otherwise
        """
        try:
            # Get children (attachments) of the item
            children = self.zot.children(item_key)
            
            for child in children:
                data = child.get("data", {})
                if data.get("contentType") == "application/pdf":
                    # Return the download URL
                    return child.get("links", {}).get("enclosure", {}).get("href")
            
            return None
        except Exception as e:
            logger.error(f"Failed to get PDF URL for item {item_key}: {e}")
            return None

    def download_pdf(self, item_key: str, output_path: Path) -> bool:
        """
        Download PDF attachment for an item.

        Args:
            item_key: Zotero item key
            output_path: Path to save the PDF

        Returns:
            True if download successful, False otherwise
        """
        try:
            # Get children (attachments) of the item
            children = self.zot.children(item_key)
            
            for child in children:
                data = child.get("data", {})
                if data.get("contentType") == "application/pdf":
                    attachment_key = child["key"]
                    
                    # Download the file
                    pdf_content = self.zot.file(attachment_key)
                    
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(pdf_content)
                    
                    logger.info(f"Downloaded PDF for item {item_key} to {output_path}")
                    return True
            
            logger.info(f"No PDF attachment found for item {item_key}")
            return False
        except Exception as e:
            logger.error(f"Failed to download PDF for item {item_key}: {e}")
            return False

    def _normalize_items(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """
        Normalize Zotero items to a consistent format.

        Args:
            items: Raw Zotero API items

        Returns:
            List of normalized item dictionaries
        """
        result = []
        for item in items:
            data = item.get("data", {})
            
            # Skip attachments and notes - we only want top-level items
            item_type = data.get("itemType", "")
            if item_type in ("attachment", "note"):
                continue

            # Extract creators/authors
            authors = []
            for creator in data.get("creators", []):
                if creator.get("creatorType") == "author":
                    name = f"{creator.get('firstName', '')} {creator.get('lastName', '')}".strip()
                    if name:
                        authors.append(name)

            # Extract year from date
            date_str = data.get("date", "")
            year = None
            if date_str:
                # Try to extract year from various date formats
                for part in date_str.split():
                    if part.isdigit() and len(part) == 4:
                        year = int(part)
                        break

            result.append({
                "key": item["key"],
                "version": item.get("version", 0),
                "item_type": self._zotero_to_standard_type(item_type),
                "title": data.get("title", ""),
                "authors": authors,
                "year": year,
                "abstract": data.get("abstractNote", ""),
                "doi": data.get("DOI", ""),
                "isbn": data.get("ISBN", ""),
                "issn": data.get("ISSN", ""),
                "url": data.get("url", ""),
                "publication": data.get("publicationTitle", "") or data.get("bookTitle", ""),
                "journal": data.get("publicationTitle", ""),
                "volume": data.get("volume", ""),
                "issue": data.get("issue", ""),
                "pages": data.get("pages", ""),
                "publisher": data.get("publisher", ""),
                "place": data.get("place", ""),
                "edition": data.get("edition", ""),
                "series": data.get("series", ""),
                "institution": data.get("institution", "") or data.get("university", ""),
                "has_pdf": any(
                    c.get("data", {}).get("contentType") == "application/pdf"
                    for c in item.get("children", [])
                ) if "children" in item else None,
            })

        return result

    def _zotero_to_standard_type(self, zotero_type: str) -> str:
        """Convert Zotero item type to standard type."""
        mapping = {
            "journalArticle": "Journal Article",
            "book": "Book",
            "bookSection": "Book Section",
            "conferencePaper": "Conference Paper",
            "report": "Report",
            "thesis": "Thesis",
            "webpage": "Web Page",
            "document": "Document",
            "manuscript": "Manuscript",
            "patent": "Patent",
            "preprint": "Preprint",
        }
        return mapping.get(zotero_type, zotero_type)


def validate_zotero_credentials(
    api_key: str,
    library_id: str,
    library_type: str = "user"
) -> Tuple[bool, Optional[str]]:
    """
    Validate Zotero API credentials without creating a persistent connection.

    Args:
        api_key: Zotero API key
        library_id: Zotero user ID or group ID  
        library_type: 'user' or 'group'

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        client = ZoteroClient(api_key, library_id, library_type)
        client.test_connection()
        return True, None
    except Exception as e:
        return False, str(e)
