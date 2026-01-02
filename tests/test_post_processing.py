"""
Test the post-processing module for MinerU output enhancement.
"""

import sys
sys.path.insert(0, ".")

from src.ingestion.post_processing import (
    detect_sections,
    remove_references_section,
    clean_ocr_artifacts,
    repair_sentence_boundaries,
    post_process_mineru_output,
    enhance_for_rag,
)


def test_section_detection():
    """Test that sections are correctly detected."""
    print("\n=== Test: Section Detection ===")
    
    markdown = """# Paper Title

## Abstract
This is the abstract of the paper.

## 1. Introduction
This paper introduces a new approach.

## 2. Methods
We used the following methods.

## 3. Results
Here are the results.

## 4. Discussion
We discuss the findings.

## References
1. Author A (2020). Title of paper.
2. Author B (2021). Another paper.
"""
    
    sections = detect_sections(markdown)
    print(f"Detected {len(sections)} sections:")
    for s in sections:
        print(f"  - {s.type}: '{s.title[:30]}...' (lines {s.start_line}-{s.end_line})")
    
    assert len(sections) >= 5, f"Expected at least 5 sections, got {len(sections)}"
    assert any(s.type == "abstract" for s in sections), "Should detect abstract"
    assert any(s.type == "methods" for s in sections), "Should detect methods"
    assert any(s.type == "references" for s in sections), "Should detect references"
    print("✓ Section detection works!")


def test_reference_removal():
    """Test that references section is removed."""
    print("\n=== Test: Reference Removal ===")
    
    markdown = """## Abstract
Important research findings.

## Methods
How we did it.

## References
1. Author A (2020). Some paper.
2. Author B (2021). Another paper.
3. Author C (2022). Third paper.

## Appendix
Additional details.
"""
    
    cleaned = remove_references_section(markdown)
    print(f"Original: {len(markdown)} chars")
    print(f"After removal: {len(cleaned)} chars")
    
    assert "## Abstract" in cleaned, "Abstract should be preserved"
    assert "## Methods" in cleaned, "Methods should be preserved"
    assert "## References" not in cleaned, "References header should be removed"
    assert "Author A (2020)" not in cleaned, "Reference entries should be removed"
    assert "## Appendix" in cleaned, "Appendix should be preserved"
    print("✓ Reference removal works!")


def test_ocr_cleanup():
    """Test OCR artifact cleanup."""
    print("\n=== Test: OCR Cleanup ===")
    
    # Sample with common OCR errors
    text = """The sample size was l23 participants.
    Page 42
    The result was signiﬁcant (p < 0.O5).
    
    This is a hyphen-
    ated word that was split.
    """
    
    cleaned = clean_ocr_artifacts(text)
    print(f"Original:\n{text}")
    print(f"Cleaned:\n{cleaned}")
    
    assert "123" in cleaned, "l -> 1 substitution should work"
    assert "0.05" in cleaned or "0.O5" not in cleaned, "O -> 0 substitution should work"
    assert "hyphenated" in cleaned, "Hyphenation should be fixed"
    assert "significant" in cleaned or "signiﬁcant" not in cleaned, "Ligatures should be fixed"
    print("✓ OCR cleanup works!")


def test_sentence_boundary_repair():
    """Test sentence boundary repair."""
    print("\n=== Test: Sentence Boundary Repair ===")
    
    text = """This is a complete sentence.
This sentence is broken across
two lines because of the PDF.
## Header should stay
This starts correctly."""
    
    repaired = repair_sentence_boundaries(text)
    print(f"Original:\n{text}")
    print(f"Repaired:\n{repaired}")
    
    assert "broken across two lines" in repaired, "Broken sentence should be joined"
    assert "## Header should stay" in repaired, "Headers should be preserved"
    print("✓ Sentence boundary repair works!")


def test_full_pipeline():
    """Test the complete post-processing pipeline."""
    print("\n=== Test: Full Pipeline ===")
    
    raw_markdown = """This is a research paper about l23 participants.
    
## Abstract
We studied the effects of intervention X.

## Methods
We used RCT methodology with l50 subjects across
multiple sites in Africa.

## Results
The effect size was signiﬁcant (d = 0.O5).

## Discussion
These ﬁndings suggest that...

## References
1. Smith, A. (2020). Paper title. Journal Name.
2. Jones, B. (2021). Another paper. Other Journal.
3. Williams, C. (2022). Third paper. Some Journal.
"""
    
    enhanced, stats = post_process_mineru_output(
        raw_markdown=raw_markdown,
        title="Test Paper on Graduation Programs",
        authors=["Smith, A.", "Jones, B.", "Williams, C.", "Brown, D."],
        year=2024,
        pdf_name="test_paper.pdf",
        remove_refs=True,
        add_header=True,
    )
    
    print(f"Stats: {stats}")
    print(f"\nEnhanced output ({len(enhanced)} chars):")
    print("-" * 60)
    print(enhanced[:1000])
    print("-" * 60)
    
    assert "# Test Paper on Graduation Programs" in enhanced, "Title header should be added"
    assert "Smith, A., Jones, B., Williams, C. et al." in enhanced, "Authors should be formatted"
    assert "2024" in enhanced, "Year should be in header"
    assert "## References" not in enhanced, "References should be removed"
    assert stats["references_removed"] == True, "Should report refs removed"
    print("✓ Full pipeline works!")


def test_enhance_for_rag():
    """Test the convenience function for Modal integration."""
    print("\n=== Test: enhance_for_rag() ===")
    
    content = """## Methods
Study conducted in l23 villages.

## References
1. Author, A. (2020). Paper.
"""
    
    enhanced = enhance_for_rag(
        content=content,
        title="RCT Study",
        year=2023,
    )
    
    print(f"Enhanced:\n{enhanced}")
    
    assert "# RCT Study" in enhanced, "Should add title"
    assert "## References" not in enhanced, "Should remove refs"
    print("✓ enhance_for_rag() works!")


if __name__ == "__main__":
    print("=" * 60)
    print("POST-PROCESSING MODULE TESTS")
    print("=" * 60)
    
    test_section_detection()
    test_reference_removal()
    test_ocr_cleanup()
    test_sentence_boundary_repair()
    test_full_pipeline()
    test_enhance_for_rag()
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED! ✓")
    print("=" * 60)
