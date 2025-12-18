"""
DevChat v2.0 SOTA - Document Loader

Handles loading and parsing of various document formats:
- Markdown files (primary format)
- PDF documents
- Structured metadata (CSV)
"""

import csv
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from llama_index.core.schema import Document
from pydantic import BaseModel

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class StudyMetadata(BaseModel):
    """Structured metadata for a study."""
    
    study_id: str
    title: str
    authors: Optional[str] = None
    year: Optional[int] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    study_type: Optional[str] = None
    confidence_rating: Optional[str] = None
    intervention_type: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    # PDF source linking (placeholder - to be populated with SharePoint URLs)
    # SharePoint folder: https://3ie.sharepoint.com/:f:/s/DEPChatbot/IgCdLWmj1g8OR5L-m5ikM-dfAZN8J2CFCpv_B5EPwZKy28o?e=hB8isv
    pdf_url: Optional[str] = None  # Direct link to PDF document
    pdf_filename: Optional[str] = None  # Original PDF filename
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for node metadata."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class DocumentLoader:
    """
    Load documents from various sources with metadata enrichment.
    
    Supports:
    - Markdown files with YAML frontmatter
    - Plain markdown files with external metadata
    - PDF files (via unstructured)
    """
    
    def __init__(
        self,
        markdown_dir: Optional[Path] = None,
        metadata_file: Optional[Path] = None,
    ):
        self.markdown_dir = markdown_dir or settings.markdown_dir
        self.metadata_file = metadata_file or settings.metadata_file
        self._metadata_cache: Dict[str, StudyMetadata] = {}
        
    def load_metadata(self) -> Dict[str, StudyMetadata]:
        """Load study metadata from CSV file."""
        if self._metadata_cache:
            return self._metadata_cache
            
        if not self.metadata_file.exists():
            logger.warning(f"Metadata file not found: {self.metadata_file}")
            return {}
        
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Normalize field names (handle various CSV column names)
                    study_id = row.get("id") or row.get("study_id") or row.get("ID", "")
                    if not study_id:
                        continue
                    
                    metadata = StudyMetadata(
                        study_id=str(study_id),
                        title=row.get("title", row.get("Title", "")),
                        authors=row.get("authors", row.get("Authors")),
                        year=self._parse_year(row.get("year", row.get("Year"))),
                        sector=row.get("sector", row.get("Sector")),
                        country=row.get("country", row.get("Country")),
                        region=row.get("region", row.get("Region")),
                        study_type=row.get("study_type", row.get("Study Type")),
                        confidence_rating=row.get("confidence_rating", row.get("Confidence")),
                        intervention_type=row.get("intervention_type", row.get("Intervention")),
                        abstract=row.get("abstract", row.get("Abstract")),
                        url=row.get("url", row.get("URL")),
                        # PDF linking fields (placeholder - to be populated)
                        pdf_url=row.get("pdf_url", row.get("PDF_URL")),
                        pdf_filename=row.get("pdf_filename", row.get("PDF_Filename")),
                    )
                    self._metadata_cache[study_id] = metadata
                    
            logger.info(f"Loaded metadata for {len(self._metadata_cache)} studies")
            
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            
        return self._metadata_cache
    
    def _parse_year(self, value: Optional[str]) -> Optional[int]:
        """Parse year from string, handling various formats."""
        if not value:
            return None
        try:
            return int(str(value)[:4])  # Handle "2023-01-15" format
        except (ValueError, TypeError):
            return None
    
    def load_markdown_files(self) -> Iterator[Document]:
        """
        Load all markdown files from the configured directory.
        
        Yields:
            Document objects with text and metadata
        """
        if not self.markdown_dir.exists():
            logger.error(f"Markdown directory not found: {self.markdown_dir}")
            return
        
        # Load metadata first
        metadata_dict = self.load_metadata()
        
        # Find all markdown files
        md_files = list(self.markdown_dir.glob("**/*.md"))
        logger.info(f"Found {len(md_files)} markdown files")
        
        for md_file in md_files:
            try:
                yield from self._load_single_markdown(md_file, metadata_dict)
            except Exception as e:
                logger.error(f"Failed to load {md_file}: {e}")
                continue
    
    def _load_single_markdown(
        self,
        file_path: Path,
        metadata_dict: Dict[str, StudyMetadata],
    ) -> Iterator[Document]:
        """Load a single markdown file."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Try to extract study ID from filename
        # Expected formats: "12345.md", "study_12345.md", "12345_title.md"
        study_id = self._extract_study_id(file_path)
        
        # Get metadata if available
        study_metadata = metadata_dict.get(study_id, None)
        
        # Build document metadata
        doc_metadata = {
            "file_path": str(file_path),
            "file_name": file_path.name,
            "study_id": study_id,
        }
        
        if study_metadata:
            doc_metadata.update(study_metadata.to_dict())
        else:
            # Try to extract metadata from markdown content itself
            extracted = self._extract_metadata_from_content(content)
            if extracted:
                doc_metadata.update(extracted)
                # Update study_id if found in content
                if "study_id" in extracted:
                    study_id = extracted["study_id"]
                    doc_metadata["study_id"] = study_id
        
        # Check for YAML frontmatter
        if content.startswith("---"):
            frontmatter, body = self._parse_frontmatter(content)
            doc_metadata.update(frontmatter)
            content = body
        
        yield Document(
            text=content,
            metadata=doc_metadata,
            doc_id=study_id,
        )
    
    def _extract_study_id(self, file_path: Path) -> str:
        """Extract study ID from filename."""
        import re
        stem = file_path.stem  # filename without extension
        
        # Try common patterns:
        # 1. "test_study_001" -> try "TEST001" first, then "001"
        # 2. "study_12345" -> try "STUDY12345", then "12345"
        # 3. "12345" -> try "12345"
        
        match = re.search(r"(\d+)", stem)
        if match:
            numeric_id = match.group(1)
            # Try with common prefixes to match metadata CSV
            for prefix in ["TEST", "STUDY", "DOC", ""]:
                candidate = f"{prefix}{numeric_id}"
                if candidate in self._metadata_cache:
                    return candidate
            # Return numeric ID if no prefix match found
            return numeric_id
        
        # Fallback to full stem (uppercase)
        if stem.upper() in self._metadata_cache:
            return stem.upper()
        return stem
    
    def _extract_metadata_from_content(self, content: str) -> Dict:
        """
        Extract metadata from markdown content.
        
        Looks for patterns like:
        - **Study ID:** TEST001
        - **Title:** Some title
        - **Authors:** Name, Name
        - **Year:** 2023
        """
        import re
        metadata = {}
        
        # Common metadata patterns in markdown
        patterns = {
            "study_id": r"\*\*Study ID:\*\*\s*(.+?)(?:\n|$)",
            "title": r"\*\*Title:\*\*\s*(.+?)(?:\n|$)",
            "authors": r"\*\*Authors?:\*\*\s*(.+?)(?:\n|$)",
            "year": r"\*\*Year:\*\*\s*(\d{4})",
            "country": r"\*\*Country:\*\*\s*(.+?)(?:\n|$)",
            "sector": r"\*\*Sector:\*\*\s*(.+?)(?:\n|$)",
            "intervention_type": r"\*\*Intervention Type:\*\*\s*(.+?)(?:\n|$)",
            "doi": r"\*\*DOI:\*\*\s*(.+?)(?:\n|$)",
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if field == "year":
                    metadata[field] = int(value)
                else:
                    metadata[field] = value
        
        # Also try to get title from first H1 heading
        if "title" not in metadata:
            h1_match = re.search(r"^#\s+(.+?)(?:\n|$)", content, re.MULTILINE)
            if h1_match:
                metadata["title"] = h1_match.group(1).strip()
        
        return metadata
    
    def _parse_frontmatter(self, content: str) -> tuple[Dict, str]:
        """Parse YAML frontmatter from markdown content."""
        try:
            import yaml
            
            # Find frontmatter boundaries
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()
                return frontmatter, body
        except Exception as e:
            logger.warning(f"Failed to parse frontmatter: {e}")
        
        return {}, content
    
    def load_pdf_files(self, pdf_dir: Optional[Path] = None) -> Iterator[Document]:
        """
        Load PDF files using unstructured (legacy method).
        
        For better extraction (tables, formulas), use load_pdfs_mineru() instead.
        
        Args:
            pdf_dir: Directory containing PDF files
            
        Yields:
            Document objects with extracted text
        """
        pdf_dir = pdf_dir or settings.data_dir / "pdfs"
        
        if not pdf_dir.exists():
            logger.warning(f"PDF directory not found: {pdf_dir}")
            return
        
        try:
            from unstructured.partition.pdf import partition_pdf
        except ImportError:
            logger.error("unstructured not installed. Run: pip install unstructured[pdf]")
            return
        
        pdf_files = list(pdf_dir.glob("**/*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files")
        
        for pdf_file in pdf_files:
            try:
                elements = partition_pdf(str(pdf_file))
                text = "\n\n".join([str(el) for el in elements])
                
                study_id = self._extract_study_id(pdf_file)
                
                yield Document(
                    text=text,
                    metadata={
                        "file_path": str(pdf_file),
                        "file_name": pdf_file.name,
                        "study_id": study_id,
                        "source_type": "pdf",
                    },
                    doc_id=study_id,
                )
            except Exception as e:
                logger.error(f"Failed to process PDF {pdf_file}: {e}")
                continue
    
    def load_pdfs_mineru(
        self,
        pdf_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        use_ocr: bool = True,
    ) -> List[Document]:
        """
        Load PDF files using MinerU for SOTA extraction.
        
        MinerU provides superior extraction for:
        - Academic papers with complex layouts
        - Tables (extracted as HTML)
        - Mathematical formulas (extracted as LaTeX)
        - Multi-column documents
        - Scanned documents (OCR)
        
        Args:
            pdf_dir: Directory containing PDF files
            output_dir: Directory for processed outputs (optional)
            use_ocr: Enable OCR for scanned pages
            
        Returns:
            List of Document objects with extracted content
        """
        pdf_dir = pdf_dir or settings.data_dir / "pdfs"
        
        if not pdf_dir.exists():
            logger.warning(f"PDF directory not found: {pdf_dir}")
            return []
        
        try:
            from src.ingestion.pdf_processor import MinerUProcessor
        except ImportError as e:
            logger.error(f"PDF processor not available: {e}")
            return []
        
        # Load metadata for enrichment
        metadata_dict = self.load_metadata()
        
        # Process PDFs with MinerU
        processor = MinerUProcessor(
            output_dir=output_dir,
            use_ocr=use_ocr,
        )
        
        results = processor.process_directory(pdf_dir, recursive=True)
        documents = processor.to_documents(results)
        
        # Enrich with external metadata if available
        for doc in documents:
            study_id = doc.metadata.get("study_id", "")
            if study_id in metadata_dict:
                external_meta = metadata_dict[study_id].to_dict()
                # Don't overwrite MinerU-extracted metadata, only add missing
                for key, value in external_meta.items():
                    if key not in doc.metadata or not doc.metadata[key]:
                        doc.metadata[key] = value
        
        logger.info(f"Loaded {len(documents)} PDFs with MinerU")
        return documents
    
    def load_all(self) -> List[Document]:
        """
        Load all documents from configured sources.
        
        Returns:
            List of all loaded documents
        """
        documents = []
        
        # Load markdown files
        documents.extend(list(self.load_markdown_files()))
        
        logger.info(f"Loaded {len(documents)} total documents")
        return documents
