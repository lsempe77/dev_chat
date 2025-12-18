"""
DevChat v2.0 SOTA - PDF Processor

Uses MinerU 2.6.x for SOTA PDF extraction:
- Text extraction with layout preservation
- Table extraction as HTML
- Formula extraction as LaTeX
- Figure detection and extraction
- OCR support for 109 languages

MinerU is AGPL-3.0 licensed - fine for internal processing
(users interact with our API, not MinerU directly)

Updated: Dec 2025 - mineru 2.6.8 API
"""

import copy
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from llama_index.core.schema import Document
from pydantic import BaseModel

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PDFMetadata(BaseModel):
    """Extracted metadata from a PDF document."""
    
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    num_pages: int = 0
    has_tables: bool = False
    has_formulas: bool = False
    table_count: int = 0
    figure_count: int = 0


class PDFProcessingResult(BaseModel):
    """Result of processing a single PDF."""
    
    success: bool
    file_path: str
    markdown_content: Optional[str] = None
    metadata: Optional[PDFMetadata] = None
    error: Optional[str] = None
    tables: List[str] = []  # HTML tables extracted
    formulas: List[str] = []  # LaTeX formulas extracted


class MinerUProcessor:
    """
    PDF processor using MinerU for SOTA extraction.
    
    Features:
    - High-quality text extraction
    - Table detection and HTML conversion
    - Formula detection and LaTeX conversion
    - Image/figure extraction
    - OCR for scanned documents (109 languages)
    """
    
    def __init__(
        self,
        output_dir: Optional[Path] = None,
        use_ocr: bool = True,
        extract_images: bool = False,
        device: str = "auto",  # "auto", "cpu", "cuda"
    ):
        """
        Initialize MinerU processor.
        
        Args:
            output_dir: Directory for processed outputs
            use_ocr: Enable OCR for scanned pages
            extract_images: Extract figures/images
            device: Device for model inference ("auto", "cpu", "cuda")
        """
        self.output_dir = output_dir or Path(tempfile.gettempdir()) / "mineru_output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_ocr = use_ocr
        self.extract_images = extract_images
        self.device = device
        
        self._mineru_available = self._check_mineru()
        
    def _check_mineru(self) -> bool:
        """Check if MinerU is installed and available."""
        try:
            # New mineru 2.6.x API
            from mineru.backend.pipeline.pipeline_analyze import doc_analyze as pipeline_doc_analyze
            from mineru.backend.pipeline.pipeline_middle_json_mkcontent import union_make as pipeline_union_make
            from mineru.backend.pipeline.model_json_to_middle_json import result_to_middle_json as pipeline_result_to_middle_json
            from mineru.data.data_reader_writer import FileBasedDataWriter
            from mineru.cli.common import prepare_env, read_fn
            from mineru.utils.enum_class import MakeMode
            logger.info("MinerU (mineru 2.6.x) is available")
            return True
        except ImportError as e:
            logger.warning(f"MinerU not available: {e}")
            logger.warning("Install with: pip install mineru[core]")
            return False
    
    def process_pdf(self, pdf_path: Path) -> PDFProcessingResult:
        """
        Process a single PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            PDFProcessingResult with markdown content and metadata
        """
        if not pdf_path.exists():
            return PDFProcessingResult(
                success=False,
                file_path=str(pdf_path),
                error=f"File not found: {pdf_path}"
            )
        
        if not self._mineru_available:
            logger.warning("MinerU not available, falling back to basic extraction")
            return self._fallback_extract(pdf_path)
        
        try:
            return self._mineru_extract(pdf_path)
        except Exception as e:
            logger.error(f"MinerU extraction failed for {pdf_path}: {e}")
            logger.info("Falling back to basic extraction")
            return self._fallback_extract(pdf_path)
    
    def _mineru_extract(self, pdf_path: Path) -> PDFProcessingResult:
        """Extract using MinerU 2.6.x pipeline backend."""
        import copy
        from mineru.backend.pipeline.pipeline_analyze import doc_analyze as pipeline_doc_analyze
        from mineru.backend.pipeline.pipeline_middle_json_mkcontent import union_make as pipeline_union_make
        from mineru.backend.pipeline.model_json_to_middle_json import result_to_middle_json as pipeline_result_to_middle_json
        from mineru.data.data_reader_writer import FileBasedDataWriter
        from mineru.cli.common import prepare_env, read_fn, convert_pdf_bytes_to_bytes_by_pypdfium2
        from mineru.utils.enum_class import MakeMode
        
        # Create output directory for this PDF
        pdf_name = pdf_path.stem
        pdf_output_dir = self.output_dir / pdf_name
        pdf_output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Processing with MinerU 2.6 pipeline: {pdf_path.name}")
        
        # Read PDF bytes
        pdf_bytes = read_fn(str(pdf_path))
        
        # method: "auto" (auto-detect), "ocr" (force OCR), "txt" (text-based)
        parse_method = "auto" if self.use_ocr else "txt"
        lang = "en"  # Default to English for academic papers
        
        # Run MinerU pipeline analysis
        infer_results, all_image_lists, all_pdf_docs, lang_list, ocr_enabled_list = pipeline_doc_analyze(
            [pdf_bytes], 
            [lang], 
            parse_method=parse_method,
            formula_enable=True,
            table_enable=True
        )
        
        if not infer_results or len(infer_results) == 0:
            return PDFProcessingResult(
                success=False,
                file_path=str(pdf_path),
                error="MinerU returned no results"
            )
        
        # Process the first (only) PDF result
        model_list = infer_results[0]
        images_list = all_image_lists[0]
        pdf_doc = all_pdf_docs[0]
        detected_lang = lang_list[0]
        ocr_enabled = ocr_enabled_list[0]
        
        # Prepare environment for output
        local_image_dir, local_md_dir = prepare_env(str(pdf_output_dir), pdf_name, parse_method)
        image_writer = FileBasedDataWriter(local_image_dir)
        md_writer = FileBasedDataWriter(local_md_dir)
        
        # Convert model results to middle JSON format
        middle_json = pipeline_result_to_middle_json(
            model_list, 
            images_list, 
            pdf_doc, 
            image_writer, 
            lang=detected_lang, 
            ocr_enable=ocr_enabled,
            formula_enabled=True
        )
        
        pdf_info = middle_json.get("pdf_info", {})
        
        # Generate markdown content
        image_dir = os.path.basename(local_image_dir)
        markdown_content = pipeline_union_make(pdf_info, MakeMode.MM_MD, image_dir)
        
        # Generate content list for tables/formulas extraction
        content_list = pipeline_union_make(pdf_info, MakeMode.CONTENT_LIST, image_dir)
        
        # Save markdown
        md_output_path = Path(local_md_dir) / f"{pdf_name}.md"
        md_writer.write_string(f"{pdf_name}.md", markdown_content)
        logger.info(f"Saved markdown to: {md_output_path}")
        
        # Save content list JSON
        md_writer.write_string(
            f"{pdf_name}_content_list.json",
            json.dumps(content_list, ensure_ascii=False, indent=4)
        )
        
        # Extract metadata from markdown content
        metadata = self._extract_metadata_from_content(markdown_content, content_list)
        
        # Get page count from pdf_info
        if isinstance(pdf_info, list):
            metadata.num_pages = len(pdf_info)
        
        # Extract tables and formulas from content list
        tables = self._extract_tables(content_list)
        formulas = self._extract_formulas(content_list)
        
        metadata.has_tables = len(tables) > 0
        metadata.has_formulas = len(formulas) > 0
        metadata.table_count = len(tables)
        
        return PDFProcessingResult(
            success=True,
            file_path=str(pdf_path),
            markdown_content=markdown_content,
            metadata=metadata,
            tables=tables,
            formulas=formulas,
        )

    def _extract_metadata_from_content(
        self,
        markdown: str,
        content_list: Any
    ) -> PDFMetadata:
        """Extract metadata from parsed content."""
        metadata = PDFMetadata()
        
        # Try to extract title from first heading
        title_match = re.search(r'^#\s+(.+)$', markdown, re.MULTILINE)
        if title_match:
            metadata.title = title_match.group(1).strip()
        
        # Try to extract abstract
        abstract_match = re.search(
            r'(?:^|\n)(?:Abstract|ABSTRACT)\s*[:\n](.+?)(?=\n\n|\n#|\n\*\*)',
            markdown,
            re.DOTALL | re.IGNORECASE
        )
        if abstract_match:
            metadata.abstract = abstract_match.group(1).strip()[:2000]  # Limit length
        
        # Try to extract DOI
        doi_match = re.search(
            r'(?:doi|DOI)[:\s]*([10]\.\d{4,}/[^\s]+)',
            markdown
        )
        if doi_match:
            metadata.doi = doi_match.group(1).strip()
        
        # Try to extract year from common patterns
        year_match = re.search(r'\b(19|20)\d{2}\b', markdown[:5000])
        if year_match:
            metadata.year = int(year_match.group(0))
        
        # Count figures
        fig_matches = re.findall(r'!\[.*?\]\(.*?\)', markdown)
        metadata.figure_count = len(fig_matches)
        
        return metadata
    
    def _extract_tables(self, content_list: Any) -> List[str]:
        """Extract HTML tables from content list.
        
        MinerU 2.6.x table structure:
        - type: "table"
        - table_body: HTML table content
        - table_caption: caption text (list)
        - table_footnote: footnote text (list)
        """
        tables = []
        if isinstance(content_list, list):
            for item in content_list:
                if isinstance(item, dict) and item.get("type") == "table":
                    # MinerU uses 'table_body' for the HTML table content
                    table_html = item.get("table_body", item.get("html", item.get("text", "")))
                    if table_html:
                        # Optionally include caption/footnote
                        caption = item.get("table_caption", [])
                        footnote = item.get("table_footnote", [])
                        
                        # Build complete table with caption if available
                        if caption and isinstance(caption, list) and caption[0]:
                            table_html = f"<caption>{caption[0]}</caption>\n{table_html}"
                        if footnote and isinstance(footnote, list) and footnote[0]:
                            table_html = f"{table_html}\n<p class='table-footnote'>{footnote[0]}</p>"
                        
                        tables.append(table_html)
        return tables
    
    def _extract_formulas(self, content_list: Any) -> List[str]:
        """Extract LaTeX formulas from content list.
        
        MinerU 2.6.x equation structure:
        - type: "equation"
        - text: LaTeX formula (with $$ delimiters)
        - text_format: "latex"
        """
        formulas = []
        if isinstance(content_list, list):
            for item in content_list:
                if isinstance(item, dict) and item.get("type") == "equation":
                    # MinerU uses 'text' field with 'text_format: latex'
                    formula = item.get("text", item.get("latex", ""))
                    if formula:
                        formulas.append(formula)
        return formulas
    
    def _fallback_extract(self, pdf_path: Path) -> PDFProcessingResult:
        """Fallback extraction using pypdf when MinerU is not available."""
        try:
            from pypdf import PdfReader
            
            reader = PdfReader(str(pdf_path))
            text_parts = []
            
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                text_parts.append(f"## Page {page_num + 1}\n\n{page_text}")
            
            markdown_content = "\n\n".join(text_parts)
            
            # Extract basic metadata
            pdf_metadata = reader.metadata or {}
            metadata = PDFMetadata(
                title=pdf_metadata.get("/Title"),
                authors=pdf_metadata.get("/Author"),
                num_pages=len(reader.pages),
            )
            
            # Try to extract year from metadata
            if pdf_metadata.get("/CreationDate"):
                year_str = str(pdf_metadata["/CreationDate"])
                year_match = re.search(r'(19|20)\d{2}', year_str)
                if year_match:
                    metadata.year = int(year_match.group(0))
            
            return PDFProcessingResult(
                success=True,
                file_path=str(pdf_path),
                markdown_content=markdown_content,
                metadata=metadata,
            )
            
        except Exception as e:
            return PDFProcessingResult(
                success=False,
                file_path=str(pdf_path),
                error=f"Fallback extraction failed: {e}"
            )
    
    def process_directory(
        self,
        pdf_dir: Path,
        recursive: bool = True,
    ) -> List[PDFProcessingResult]:
        """
        Process all PDFs in a directory.
        
        Args:
            pdf_dir: Directory containing PDFs
            recursive: Search subdirectories
            
        Returns:
            List of processing results
        """
        pattern = "**/*.pdf" if recursive else "*.pdf"
        pdf_files = list(pdf_dir.glob(pattern))
        
        logger.info(f"Found {len(pdf_files)} PDFs in {pdf_dir}")
        
        results = []
        for i, pdf_path in enumerate(pdf_files, 1):
            logger.info(f"Processing [{i}/{len(pdf_files)}]: {pdf_path.name}")
            result = self.process_pdf(pdf_path)
            results.append(result)
            
            if result.success:
                logger.info(f"  ✓ Extracted {len(result.markdown_content or '')} chars")
            else:
                logger.error(f"  ✗ Failed: {result.error}")
        
        # Summary
        success_count = sum(1 for r in results if r.success)
        logger.info(f"Processed {success_count}/{len(results)} PDFs successfully")
        
        return results
    
    def to_documents(
        self,
        results: List[PDFProcessingResult],
        base_metadata: Optional[Dict] = None,
    ) -> List[Document]:
        """
        Convert processing results to LlamaIndex Documents.
        
        Args:
            results: List of PDFProcessingResult
            base_metadata: Additional metadata to add to all documents
            
        Returns:
            List of Document objects ready for chunking/embedding
        """
        documents = []
        
        for result in results:
            if not result.success or not result.markdown_content:
                continue
            
            # Build metadata
            doc_metadata = base_metadata.copy() if base_metadata else {}
            doc_metadata["file_path"] = result.file_path
            doc_metadata["source_type"] = "pdf"
            
            if result.metadata:
                if result.metadata.title:
                    doc_metadata["title"] = result.metadata.title
                if result.metadata.authors:
                    doc_metadata["authors"] = result.metadata.authors
                if result.metadata.year:
                    doc_metadata["year"] = result.metadata.year
                if result.metadata.doi:
                    doc_metadata["doi"] = result.metadata.doi
                if result.metadata.abstract:
                    doc_metadata["abstract"] = result.metadata.abstract
                doc_metadata["num_pages"] = result.metadata.num_pages
                doc_metadata["has_tables"] = result.metadata.has_tables
                doc_metadata["has_formulas"] = result.metadata.has_formulas
                doc_metadata["table_count"] = result.metadata.table_count
                doc_metadata["figure_count"] = result.metadata.figure_count
            
            # Generate study_id from filename
            pdf_path = Path(result.file_path)
            study_id = pdf_path.stem  # filename without extension
            doc_metadata["study_id"] = study_id
            doc_metadata["pdf_filename"] = pdf_path.name
            
            documents.append(Document(
                text=result.markdown_content,
                metadata=doc_metadata,
                doc_id=study_id,
            ))
        
        logger.info(f"Created {len(documents)} Documents from PDF results")
        return documents


# Convenience function for simple usage
def process_pdfs(
    pdf_dir: Path,
    output_dir: Optional[Path] = None,
    **kwargs
) -> List[Document]:
    """
    Process all PDFs in a directory and return LlamaIndex Documents.
    
    Args:
        pdf_dir: Directory containing PDF files
        output_dir: Optional output directory for processed files
        **kwargs: Additional arguments passed to MinerUProcessor
        
    Returns:
        List of Document objects ready for ingestion
    """
    processor = MinerUProcessor(output_dir=output_dir, **kwargs)
    results = processor.process_directory(pdf_dir)
    return processor.to_documents(results)
