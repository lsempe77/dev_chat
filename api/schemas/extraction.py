"""
DevChat v2.0 - Extraction Pipeline Schemas

Pydantic models for extracted effect sizes and treatment effects.
Used by the API to serve quantitative evidence to the chatbot.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, computed_field


# =============================================================================
# Enums
# =============================================================================

class ExtractionMethod(str, Enum):
    """How the estimate was extracted."""
    PIPELINE = "pipeline"  # Automated extraction pipeline
    MANUAL = "manual"  # Human-entered
    LLM_PROSE = "llm_prose"  # Extracted from narrative text
    FIGURE = "figure"  # Extracted from figure captions


class StudyDesign(str, Enum):
    """Study design types."""
    RCT = "RCT"
    DID = "DiD"
    RDD = "RDD"
    IV = "IV"
    PSM = "Propensity score matching"
    MIXED = "Mixed methods"
    OTHER = "Other"


class OutcomeCategory(str, Enum):
    """Standardized outcome categories."""
    INCOME = "Income"
    ASSETS = "Assets"
    CONSUMPTION = "Consumption"
    EXPENDITURE = "Expenditure"
    SAVINGS = "Savings"
    EMPLOYMENT = "Employment"
    HEALTH = "Health"
    EDUCATION = "Education"
    FOOD_SECURITY = "Food security"
    PSYCHOLOGICAL = "Psychological"
    SOCIAL = "Social"
    OTHER = "Other"


# =============================================================================
# Core Models
# =============================================================================

class ExtractedEstimateBase(BaseModel):
    """Base model for extracted effect estimates."""
    
    # Effect identification
    treatment_arm: str = Field(description="Treatment group name")
    outcome_name: str = Field(description="Outcome variable name")
    outcome_category: Optional[str] = Field(default=None, description="Standardized outcome category")
    
    # Primary effect statistics
    coefficient: Optional[float] = Field(default=None, description="Point estimate")
    standard_error: Optional[float] = Field(default=None, description="Standard error")
    p_value: Optional[float] = Field(default=None, description="P-value")
    ci_lower: Optional[float] = Field(default=None, description="95% CI lower bound")
    ci_upper: Optional[float] = Field(default=None, description="95% CI upper bound")
    
    # Sample sizes
    sample_size: Optional[int] = Field(default=None, description="Total sample size")
    n_treatment: Optional[int] = Field(default=None, description="Treatment group N")
    n_control: Optional[int] = Field(default=None, description="Control group N")
    
    # Control group statistics
    control_mean: Optional[float] = Field(default=None, description="Control group mean")
    control_sd: Optional[float] = Field(default=None, description="Control group SD")
    
    # Standardized effect sizes
    cohens_d: Optional[float] = Field(default=None, description="Cohen's d")
    hedges_g: Optional[float] = Field(default=None, description="Hedges' g (bias-corrected)")
    effect_size_assumption: Optional[str] = Field(default=None, description="How effect size was calculated")
    
    # Effect classification
    is_main_effect: bool = Field(default=True, description="Is this a main effect?")
    is_subgroup: bool = Field(default=False, description="Is this a subgroup analysis?")
    subgroup_variable: Optional[str] = Field(default=None, description="Subgroup variable name")


class ExtractedEstimateCreate(ExtractedEstimateBase):
    """Model for creating a new extracted estimate."""
    
    # Study identification
    study_id: str = Field(description="Study/document identifier")
    document_id: Optional[UUID] = Field(default=None, description="Link to documents table")
    rag_project_id: Optional[UUID] = Field(default=None, description="Link to RAG project")
    
    # Source table info
    table_number: Optional[str] = Field(default=None, description="Source table number")
    table_caption: Optional[str] = Field(default=None, description="Table caption")
    page_number: Optional[int] = Field(default=None, description="Page number in PDF")
    pdf_name: Optional[str] = Field(default=None, description="Original PDF filename")
    
    # Study metadata
    authors: Optional[str] = Field(default=None, description="Study authors")
    year: Optional[int] = Field(default=None, description="Publication year")
    country: Optional[str] = Field(default=None, description="Study country")
    study_design: Optional[str] = Field(default=None, description="Study design")
    
    # Extraction metadata
    extraction_confidence: Optional[float] = Field(default=None, description="Extraction confidence 0-1")
    extraction_method: str = Field(default="pipeline", description="Extraction method")
    extraction_version: Optional[str] = Field(default=None, description="Pipeline version")


class ExtractedEstimate(ExtractedEstimateCreate):
    """Full extracted estimate model with DB fields."""
    
    id: UUID = Field(description="Database ID")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    effect_summary: Optional[str] = Field(default=None, description="Auto-generated summary")
    
    @computed_field
    @property
    def significance_level(self) -> Optional[str]:
        """Human-readable significance level."""
        if self.p_value is None:
            return None
        if self.p_value < 0.001:
            return "***"
        elif self.p_value < 0.01:
            return "**"
        elif self.p_value < 0.05:
            return "*"
        elif self.p_value < 0.1:
            return "†"
        return "ns"
    
    @computed_field
    @property
    def effect_magnitude(self) -> Optional[str]:
        """Human-readable effect size interpretation (Cohen's conventions)."""
        d = self.cohens_d or self.hedges_g
        if d is None:
            return None
        abs_d = abs(d)
        if abs_d < 0.2:
            return "negligible"
        elif abs_d < 0.5:
            return "small"
        elif abs_d < 0.8:
            return "medium"
        return "large"
    
    class Config:
        from_attributes = True


# =============================================================================
# Batch Operations
# =============================================================================

class BulkUploadRequest(BaseModel):
    """Request to upload multiple extracted estimates."""
    
    estimates: List[ExtractedEstimateCreate] = Field(
        description="List of estimates to upload",
        min_length=1,
        max_length=1000
    )
    upsert: bool = Field(
        default=True,
        description="If true, update existing records by study_id + outcome_name"
    )


class BulkUploadResponse(BaseModel):
    """Response from bulk upload."""
    
    success: bool
    inserted: int = Field(description="Number of new records inserted")
    updated: int = Field(description="Number of existing records updated")
    errors: List[Dict[str, Any]] = Field(default=[], description="Any errors encountered")


# =============================================================================
# Query Models
# =============================================================================

class EstimateQuery(BaseModel):
    """Query parameters for searching estimates."""
    
    study_ids: Optional[List[str]] = Field(default=None, description="Filter by study IDs")
    outcome_categories: Optional[List[str]] = Field(default=None, description="Filter by outcome categories")
    countries: Optional[List[str]] = Field(default=None, description="Filter by countries")
    study_designs: Optional[List[str]] = Field(default=None, description="Filter by study designs")
    min_year: Optional[int] = Field(default=None, description="Minimum publication year")
    max_year: Optional[int] = Field(default=None, description="Maximum publication year")
    main_effects_only: bool = Field(default=False, description="Only return main effects")
    has_effect_size: bool = Field(default=False, description="Only return estimates with Cohen's d")
    
    # Pagination
    limit: int = Field(default=100, le=1000, description="Max results to return")
    offset: int = Field(default=0, description="Offset for pagination")


class EstimateQueryResponse(BaseModel):
    """Response from estimate query."""
    
    estimates: List[ExtractedEstimate]
    total: int = Field(description="Total matching estimates")
    limit: int
    offset: int


# =============================================================================
# Aggregation Models (for chatbot context)
# =============================================================================

class StudyEffectSummary(BaseModel):
    """Aggregated summary of effects for a single study."""
    
    study_id: str
    authors: Optional[str]
    year: Optional[int]
    country: Optional[str]
    study_design: Optional[str]
    
    # Aggregated stats
    total_effects: int
    main_effects: int
    outcome_categories: List[str]
    
    # Effect size summary
    avg_cohens_d: Optional[float]
    avg_hedges_g: Optional[float]
    min_p_value: Optional[float]
    
    @computed_field
    @property
    def citation(self) -> str:
        """Generate citation string."""
        parts = []
        if self.authors:
            # Take first author surname
            first_author = self.authors.split(",")[0].split()[-1] if self.authors else "Unknown"
            parts.append(first_author)
        if self.year:
            parts.append(f"({self.year})")
        return " ".join(parts) if parts else self.study_id


class OutcomeMetaAnalysis(BaseModel):
    """Cross-study aggregation for an outcome category."""
    
    outcome_category: str
    n_studies: int
    n_estimates: int
    
    # Pooled effect sizes
    pooled_cohens_d: Optional[float]
    pooled_hedges_g: Optional[float]
    sd_cohens_d: Optional[float]
    median_cohens_d: Optional[float]
    
    @computed_field
    @property
    def evidence_strength(self) -> str:
        """Interpret the pooled evidence."""
        if self.n_studies < 3:
            return "limited"
        elif self.n_studies < 5:
            return "moderate"
        elif self.n_studies < 10:
            return "substantial"
        return "strong"
    
    @computed_field
    @property
    def summary_for_chatbot(self) -> str:
        """Generate a natural language summary for RAG context."""
        d = self.pooled_cohens_d
        magnitude = "negligible" if d is None else (
            "negligible" if abs(d) < 0.2 else
            "small" if abs(d) < 0.5 else
            "medium" if abs(d) < 0.8 else "large"
        )
        direction = "positive" if d and d > 0 else "negative" if d and d < 0 else "mixed"
        
        return (
            f"Across {self.n_studies} studies ({self.n_estimates} estimates), "
            f"{self.outcome_category} outcomes show a {magnitude} {direction} effect "
            f"(pooled d = {d:.3f})" if d else f"({self.n_estimates} estimates)"
        )


class EvidencePanelData(BaseModel):
    """Data structure for the frontend Evidence Panel."""
    
    study_summaries: List[StudyEffectSummary]
    outcome_summaries: List[OutcomeMetaAnalysis]
    
    # Quick stats
    total_studies: int
    total_estimates: int
    countries: List[str]
    study_designs: List[str]
    year_range: Optional[tuple[int, int]]


# =============================================================================
# Chatbot Integration Models
# =============================================================================

class QuantitativeContext(BaseModel):
    """
    Quantitative evidence context for the chatbot.
    
    This model packages extracted effect sizes in a format optimized
    for inclusion in RAG prompts and synthesis responses.
    """
    
    query_relevant_estimates: List[ExtractedEstimate] = Field(
        description="Estimates relevant to the user's query"
    )
    outcome_summaries: List[OutcomeMetaAnalysis] = Field(
        description="Cross-study aggregation by outcome"
    )
    
    # Natural language summaries
    evidence_narrative: str = Field(
        description="Pre-generated narrative summary for the chatbot"
    )
    
    @computed_field
    @property
    def has_quantitative_evidence(self) -> bool:
        """Whether any quantitative evidence was found."""
        return len(self.query_relevant_estimates) > 0


class ChatbotEffectContext(BaseModel):
    """
    Compact effect context for chatbot prompts.
    
    Designed to be injected into synthesis prompts with minimal tokens
    but maximum information for accurate quantitative claims.
    """
    
    # Compact study-level data
    studies: List[Dict[str, Any]] = Field(
        description="Compact study data for prompt injection"
    )
    
    # Pre-computed aggregates
    pooled_effects: Dict[str, float] = Field(
        default={},
        description="Pooled effect sizes by outcome category"
    )
    
    # Metadata
    n_studies: int
    n_estimates: int
    
    def to_prompt_context(self) -> str:
        """Generate prompt-ready context string."""
        lines = [f"**Quantitative Evidence ({self.n_studies} studies, {self.n_estimates} estimates)**"]
        
        for study in self.studies[:10]:  # Limit to prevent prompt overflow
            authors = study.get("authors", "Unknown")
            year = study.get("year", "")
            effect = study.get("avg_effect", "N/A")
            outcomes = ", ".join(study.get("outcomes", [])[:3])
            lines.append(f"- {authors} ({year}): {outcomes} (avg d={effect})")
        
        if self.pooled_effects:
            lines.append("\n**Pooled Effects:**")
            for outcome, d in self.pooled_effects.items():
                lines.append(f"- {outcome}: d = {d:.3f}")
        
        return "\n".join(lines)
