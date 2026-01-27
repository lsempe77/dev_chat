"""
Topic-Agnostic Extraction Schema for DevChat Pipeline
======================================================

Generic schema that works for ANY systematic review topic:
- Aquaculture
- Education
- Health
- Poverty/graduation programs
- Agriculture
- Any other domain

Core principle: Separate UNIVERSAL fields from DOMAIN-SPECIFIC fields.
"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum


# =============================================================================
# UNIVERSAL CORE FIELDS (Apply to ALL quantitative research)
# =============================================================================

class CoreNumericFields(BaseModel):
    """
    Universal effect size fields that appear in ANY quantitative study.
    These are the regression/statistical outputs common across all domains.
    """
    
    # Primary effect estimate (could be coefficient, odds ratio, mean diff, etc.)
    effect_estimate: Optional[float] = Field(None, 
        description="Primary effect estimate (coefficient, OR, RR, mean difference, etc.)")
    effect_type: Optional[str] = Field(None,
        description="Type of effect: 'coefficient', 'odds_ratio', 'risk_ratio', 'mean_diff', 'smd', etc.")
    
    # Precision measures
    standard_error: Optional[float] = Field(None, description="Standard error of estimate")
    variance: Optional[float] = Field(None, description="Variance of estimate")
    
    # Test statistics
    test_statistic: Optional[float] = Field(None, description="t-stat, z-stat, chi-square, F, etc.")
    test_type: Optional[str] = Field(None, description="Type: 't', 'z', 'chi2', 'F'")
    degrees_of_freedom: Optional[float] = Field(None, description="Degrees of freedom")
    
    # Confidence intervals
    ci_lower: Optional[float] = Field(None, description="CI lower bound")
    ci_upper: Optional[float] = Field(None, description="CI upper bound")
    ci_level: Optional[float] = Field(0.95, description="CI level (default 95%)")
    
    # P-value (multiple formats)
    p_value: Optional[float] = Field(None, description="Numeric p-value if available")
    p_value_text: Optional[str] = Field(None, description="Text p-value (e.g., 'p<0.05', 'p>.1', 'NS')")
    significance_level: Optional[str] = Field(None, description="Asterisks: *, **, ***, †")
    
    # Sample sizes
    n_total: Optional[int] = Field(None, description="Total sample size")
    n_treatment: Optional[int] = Field(None, description="Treatment/intervention group N")
    n_control: Optional[int] = Field(None, description="Control/comparison group N")
    n_groups: Optional[int] = Field(None, description="Number of groups/arms")
    
    # Clustering (if applicable)
    n_clusters: Optional[int] = Field(None, description="Number of clusters if cluster-randomized")
    cluster_unit: Optional[str] = Field(None, description="What is clustered: 'school', 'village', 'clinic', etc.")
    
    # Time/panel
    n_time_periods: Optional[int] = Field(None, description="Number of time points")
    follow_up_duration: Optional[float] = Field(None, description="Follow-up duration")
    follow_up_unit: Optional[str] = Field(None, description="Unit: 'days', 'weeks', 'months', 'years'")


class StudyMetadata(BaseModel):
    """
    Universal bibliographic information for ANY study.
    """
    
    # Identifiers
    study_id: Optional[str] = Field(None, description="Unique study ID (DOI, internal ID, etc.)")
    estimate_id: Optional[str] = Field(None, description="Unique estimate ID within study")
    
    # Citation info
    authors: Optional[str] = Field(None, description="Author names")
    year: Optional[int] = Field(None, description="Publication year")
    title: Optional[str] = Field(None, description="Study title")
    journal: Optional[str] = Field(None, description="Journal/source")
    doi: Optional[str] = Field(None, description="DOI if available")
    
    # Geography
    country: Optional[str] = Field(None, description="Country/countries")
    region: Optional[str] = Field(None, description="Region/state/province")
    setting: Optional[str] = Field(None, description="Urban/rural/mixed")
    
    # Study design
    study_design: Optional[str] = Field(None, 
        description="RCT, quasi-experimental, DiD, RDD, IV, observational, etc.")
    is_experimental: Optional[bool] = Field(None, description="True if randomized")


class OutcomeMetadata(BaseModel):
    """
    Universal outcome description - works for any domain.
    """
    
    # What's being measured
    outcome_name: Optional[str] = Field(None, description="Specific outcome variable name")
    outcome_description: Optional[str] = Field(None, description="Full description of outcome")
    outcome_domain: Optional[str] = Field(None, 
        description="Broad domain: 'economic', 'health', 'education', 'environment', 'behavioral', etc.")
    
    # Measurement details
    outcome_type: Optional[str] = Field(None, 
        description="Continuous, binary, count, ordinal, time-to-event")
    outcome_unit: Optional[str] = Field(None, description="Unit of measurement")
    outcome_scale: Optional[str] = Field(None, description="Scale name if standardized (e.g., 'PHQ-9', 'test scores')")
    
    # Direction
    higher_is_better: Optional[bool] = Field(None, 
        description="True if higher values = better outcome")


class InterventionMetadata(BaseModel):
    """
    Universal intervention description - topic-agnostic.
    """
    
    intervention_name: Optional[str] = Field(None, description="Name of intervention")
    intervention_description: Optional[str] = Field(None, description="Full description")
    intervention_type: Optional[str] = Field(None, 
        description="Category: 'treatment', 'program', 'policy', 'technology', 'training', etc.")
    
    # Comparison
    control_name: Optional[str] = Field(None, description="What control group received")
    control_type: Optional[str] = Field(None, 
        description="'no treatment', 'placebo', 'treatment as usual', 'active control', etc.")
    
    # Dosage/intensity (if applicable)
    duration: Optional[float] = Field(None, description="Intervention duration")
    duration_unit: Optional[str] = Field(None, description="Unit: days, weeks, months")
    intensity: Optional[str] = Field(None, description="Frequency/intensity description")


class SourceLocation(BaseModel):
    """
    Where in the paper the data came from.
    """
    
    page_number: Optional[int] = Field(None)
    table_number: Optional[str] = Field(None, description="Table number or identifier")
    table_title: Optional[str] = Field(None, description="Full table title")
    figure_number: Optional[str] = Field(None, description="If from a figure")
    
    row_identifier: Optional[str] = Field(None, description="Row label or description")
    column_identifier: Optional[str] = Field(None, description="Column label or description")
    
    # Table format (helps with parsing)
    table_format: Optional[str] = Field(None, 
        description="Format pattern: 'coef_se_pvalue', 'coef_ci', 'coef_se_stars', etc.")
    
    # Text mention
    mentioned_in_text: Optional[bool] = Field(None)
    text_context: Optional[str] = Field(None, description="Surrounding text if mentioned")


# =============================================================================
# CALCULATED/DERIVED FIELDS (Computed post-extraction)
# =============================================================================

class StandardizedEffectSize(BaseModel):
    """
    Calculated effect sizes for meta-analysis - computed, not extracted.
    """
    
    # Standardized effect
    cohens_d: Optional[float] = Field(None, description="Cohen's d")
    hedges_g: Optional[float] = Field(None, description="Hedges' g (bias-corrected)")
    
    # For binary outcomes
    log_odds_ratio: Optional[float] = Field(None)
    log_risk_ratio: Optional[float] = Field(None)
    
    # Variance
    effect_variance: Optional[float] = Field(None, description="Variance of standardized effect")
    effect_se: Optional[float] = Field(None, description="SE of standardized effect")
    
    # Adjusted CI
    ci_lower_std: Optional[float] = Field(None)
    ci_upper_std: Optional[float] = Field(None)
    
    # Bias correction
    small_sample_correction: Optional[float] = Field(None, description="J correction factor")


# =============================================================================
# DOMAIN-SPECIFIC EXTENSIONS (Configurable per topic)
# =============================================================================

class DomainSpecificFields(BaseModel):
    """
    Flexible container for domain-specific fields.
    Configure these based on the systematic review topic.
    
    Examples:
    - Graduation programs: intervention_components (health, skills, savings, etc.)
    - Education: grade_level, subject_area, teacher_training
    - Health: condition, treatment_modality, dosage
    - Agriculture: crop_type, farming_system, climate_zone
    """
    
    # Generic key-value store for domain fields
    domain: Optional[str] = Field(None, description="Domain name: 'graduation', 'education', 'health', etc.")
    
    # Flexible fields - schema defined per domain
    custom_fields: Optional[dict[str, Any]] = Field(default_factory=dict,
        description="Domain-specific fields as key-value pairs")
    
    # Domain-specific outcome categorization
    outcome_category: Optional[str] = Field(None, 
        description="Domain-specific outcome category (e.g., 'Assets', 'Test scores', 'Mortality')")
    outcome_subcategory: Optional[str] = Field(None)
    
    # Domain-specific intervention components
    intervention_components: Optional[list[str]] = Field(None,
        description="List of intervention components relevant to domain")


# =============================================================================
# COMPLETE EXTRACTION RECORD
# =============================================================================

class ExtractedEstimate(BaseModel):
    """
    Complete extraction record for one effect size estimate.
    Works for ANY systematic review topic.
    """
    
    # Universal fields (required for all topics)
    numeric: CoreNumericFields = Field(default_factory=CoreNumericFields)
    study: StudyMetadata = Field(default_factory=StudyMetadata)
    outcome: OutcomeMetadata = Field(default_factory=OutcomeMetadata)
    intervention: InterventionMetadata = Field(default_factory=InterventionMetadata)
    source: SourceLocation = Field(default_factory=SourceLocation)
    
    # Calculated (filled post-extraction)
    standardized: StandardizedEffectSize = Field(default_factory=StandardizedEffectSize)
    
    # Domain-specific (configured per SR)
    domain_fields: DomainSpecificFields = Field(default_factory=DomainSpecificFields)
    
    # Extraction metadata
    extraction_confidence: Optional[float] = Field(None, description="Confidence 0-1")
    extraction_method: Optional[str] = Field(None, description="'table_parse', 'llm_extract', 'manual'")
    extraction_notes: Optional[str] = Field(None)
    needs_review: Optional[bool] = Field(False, description="Flag for human review")


# =============================================================================
# DOMAIN CONFIGURATION EXAMPLES
# =============================================================================

# These define what domain-specific fields to extract for each topic

DOMAIN_CONFIGS = {
    "graduation": {
        "outcome_categories": ["Assets", "Income", "Expenditure", "Savings", "Poverty", "Food Security", "Wellbeing"],
        "intervention_components": [
            "consumption_support", "asset_transfer", "health_component", 
            "skills_training", "savings_facilitation", "coaching", "social_integration"
        ],
        "custom_fields": ["targeting_women", "cash_control", "program_duration"]
    },
    
    "education": {
        "outcome_categories": ["Test Scores", "Enrollment", "Attendance", "Graduation", "Learning", "Behavior"],
        "intervention_components": [
            "teacher_training", "curriculum", "technology", "infrastructure",
            "incentives", "tutoring", "parental_engagement"
        ],
        "custom_fields": ["grade_level", "subject_area", "school_type", "student_age"]
    },
    
    "health": {
        "outcome_categories": ["Mortality", "Morbidity", "Service Use", "Knowledge", "Behavior", "Biomarkers"],
        "intervention_components": [
            "treatment", "prevention", "screening", "counseling", 
            "community_health_worker", "mhealth", "supply_side", "demand_side"
        ],
        "custom_fields": ["condition", "age_group", "facility_level", "delivery_mode"]
    },
    
    "agriculture": {
        "outcome_categories": ["Yield", "Income", "Adoption", "Productivity", "Food Security", "Environment"],
        "intervention_components": [
            "inputs", "training", "extension", "credit", "insurance",
            "market_access", "irrigation", "mechanization"
        ],
        "custom_fields": ["crop_type", "farming_system", "climate_zone", "farm_size"]
    },
    
    "aquaculture": {
        "outcome_categories": ["Production", "Income", "Adoption", "Environmental", "Food Security"],
        "intervention_components": [
            "feed_management", "water_quality", "species_selection", "training",
            "credit", "market_linkages", "biosecurity"
        ],
        "custom_fields": ["species", "production_system", "water_type", "scale"]
    },
    
    "wash": {
        "outcome_categories": ["Diarrhea", "Mortality", "Access", "Behavior", "Water Quality", "Nutrition"],
        "intervention_components": [
            "water_supply", "sanitation", "hygiene_promotion", "handwashing",
            "chlorination", "filters", "latrines"
        ],
        "custom_fields": ["water_source", "sanitation_type", "target_population"]
    },
    
    "nutrition": {
        "outcome_categories": ["Stunting", "Wasting", "Underweight", "Anemia", "Micronutrients", "Diet Quality"],
        "intervention_components": [
            "supplementation", "fortification", "counseling", "cash_transfer",
            "school_feeding", "agriculture", "social_protection"
        ],
        "custom_fields": ["age_group", "supplement_type", "delivery_platform"]
    },
    
    "social_protection": {
        "outcome_categories": ["Income", "Consumption", "Poverty", "Labor", "Education", "Health", "Empowerment"],
        "intervention_components": [
            "cash_transfer", "in_kind", "public_works", "insurance",
            "pensions", "conditions", "targeting"
        ],
        "custom_fields": ["transfer_size", "transfer_frequency", "conditionality", "targeting_method"]
    },
    
    "generic": {
        "outcome_categories": ["Primary", "Secondary", "Tertiary"],
        "intervention_components": [],
        "custom_fields": []
    }
}


# =============================================================================
# EXTRACTION MODES
# =============================================================================

class ExtractionMode(str, Enum):
    """Extraction depth modes."""
    RAG = "rag"           # Quick extraction for chat (10-15 key fields)
    SCREENING = "screening"  # For title/abstract screening
    FULL = "full"         # Complete SR extraction (all fields)


# Fields to extract per mode
EXTRACTION_FIELDS = {
    ExtractionMode.RAG: [
        "numeric.effect_estimate",
        "numeric.standard_error", 
        "numeric.p_value_text",
        "numeric.n_total",
        "study.authors",
        "study.year",
        "study.country",
        "study.study_design",
        "outcome.outcome_name",
        "outcome.outcome_domain",
        "intervention.intervention_name",
    ],
    
    ExtractionMode.SCREENING: [
        "study.authors",
        "study.year", 
        "study.title",
        "study.country",
        "study.study_design",
        "intervention.intervention_type",
        "outcome.outcome_domain",
    ],
    
    ExtractionMode.FULL: ["*"],  # All fields
}


def get_domain_config(domain: str) -> dict:
    """Get the configuration for a specific domain."""
    return DOMAIN_CONFIGS.get(domain, DOMAIN_CONFIGS["generic"])


def list_available_domains() -> list[str]:
    """List all available domain configurations."""
    return list(DOMAIN_CONFIGS.keys())


if __name__ == "__main__":
    # Example: Education study
    estimate = ExtractedEstimate(
        numeric=CoreNumericFields(
            effect_estimate=0.25,
            effect_type="smd",
            standard_error=0.08,
            p_value=0.002,
            n_total=1500,
            n_treatment=750,
            n_control=750
        ),
        study=StudyMetadata(
            authors="Smith et al.",
            year=2024,
            country="Kenya",
            study_design="cluster-RCT",
            is_experimental=True
        ),
        outcome=OutcomeMetadata(
            outcome_name="Math test scores",
            outcome_domain="education",
            outcome_type="continuous",
            outcome_scale="standardized test"
        ),
        intervention=InterventionMetadata(
            intervention_name="Tablet-based learning",
            intervention_type="technology",
            control_type="treatment as usual"
        ),
        domain_fields=DomainSpecificFields(
            domain="education",
            outcome_category="Test Scores",
            intervention_components=["technology", "curriculum"],
            custom_fields={
                "grade_level": "primary",
                "subject_area": "math",
                "school_type": "public"
            }
        )
    )
    
    print("Sample Education Study Extraction:")
    print(estimate.model_dump_json(indent=2))
    
    print("\n\nAvailable Domain Configs:")
    for domain, config in DOMAIN_CONFIGS.items():
        print(f"\n{domain.upper()}:")
        print(f"  Outcomes: {config['outcome_categories']}")
        comps = config['intervention_components'][:3]
        if len(config['intervention_components']) > 3:
            print(f"  Components: {comps}... (+{len(config['intervention_components'])-3} more)")
        else:
            print(f"  Components: {comps}")
