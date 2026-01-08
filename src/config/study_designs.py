"""
Study Design Classification Configuration

Defines the taxonomy of study designs used in development research,
with classification prompts and display labels.
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass


class StudyDesign(str, Enum):
    """
    Taxonomy of study designs for development research.
    
    Organized by evidence hierarchy:
    1. Experimental (highest causal inference)
    2. Quasi-experimental
    3. Observational
    4. Qualitative
    5. Other
    """
    
    # Experimental
    RCT = "rct"
    CLUSTER_RCT = "cluster_rct"
    
    # Quasi-experimental
    REGRESSION_DISCONTINUITY = "regression_discontinuity"
    DIFFERENCE_IN_DIFFERENCES = "difference_in_differences"
    INSTRUMENTAL_VARIABLE = "instrumental_variable"
    PROPENSITY_SCORE_MATCHING = "propensity_score_matching"
    INTERRUPTED_TIME_SERIES = "interrupted_time_series"
    SYNTHETIC_CONTROL = "synthetic_control"
    
    # Observational
    COHORT = "cohort"
    CROSS_SECTIONAL = "cross_sectional"
    CASE_CONTROL = "case_control"
    PANEL = "panel"
    
    # Qualitative
    QUALITATIVE = "qualitative"
    MIXED_METHODS = "mixed_methods"
    CASE_STUDY = "case_study"
    ETHNOGRAPHY = "ethnography"
    
    # Synthesis
    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    
    # Other
    MODELING = "modeling"
    DESCRIPTIVE = "descriptive"
    THEORY = "theory"
    UNKNOWN = "unknown"


@dataclass
class StudyDesignInfo:
    """Information about a study design type."""
    code: str
    label: str
    short_label: str
    category: str
    evidence_weight: float  # 0.0-1.0, higher = stronger causal evidence
    color: str  # For UI badges


# Study design metadata for UI and weighting
STUDY_DESIGN_INFO: Dict[StudyDesign, StudyDesignInfo] = {
    # Experimental (weight: 1.0)
    StudyDesign.RCT: StudyDesignInfo(
        code="rct", label="Randomized Controlled Trial", short_label="RCT",
        category="Experimental", evidence_weight=1.0, color="green"
    ),
    StudyDesign.CLUSTER_RCT: StudyDesignInfo(
        code="cluster_rct", label="Cluster Randomized Trial", short_label="Cluster RCT",
        category="Experimental", evidence_weight=0.95, color="green"
    ),
    
    # Quasi-experimental (weight: 0.7-0.85)
    StudyDesign.REGRESSION_DISCONTINUITY: StudyDesignInfo(
        code="regression_discontinuity", label="Regression Discontinuity", short_label="RDD",
        category="Quasi-experimental", evidence_weight=0.85, color="blue"
    ),
    StudyDesign.DIFFERENCE_IN_DIFFERENCES: StudyDesignInfo(
        code="difference_in_differences", label="Difference-in-Differences", short_label="DiD",
        category="Quasi-experimental", evidence_weight=0.80, color="blue"
    ),
    StudyDesign.INSTRUMENTAL_VARIABLE: StudyDesignInfo(
        code="instrumental_variable", label="Instrumental Variable", short_label="IV",
        category="Quasi-experimental", evidence_weight=0.80, color="blue"
    ),
    StudyDesign.PROPENSITY_SCORE_MATCHING: StudyDesignInfo(
        code="propensity_score_matching", label="Propensity Score Matching", short_label="PSM",
        category="Quasi-experimental", evidence_weight=0.75, color="blue"
    ),
    StudyDesign.INTERRUPTED_TIME_SERIES: StudyDesignInfo(
        code="interrupted_time_series", label="Interrupted Time Series", short_label="ITS",
        category="Quasi-experimental", evidence_weight=0.75, color="blue"
    ),
    StudyDesign.SYNTHETIC_CONTROL: StudyDesignInfo(
        code="synthetic_control", label="Synthetic Control", short_label="SC",
        category="Quasi-experimental", evidence_weight=0.80, color="blue"
    ),
    
    # Observational (weight: 0.4-0.6)
    StudyDesign.COHORT: StudyDesignInfo(
        code="cohort", label="Cohort Study", short_label="Cohort",
        category="Observational", evidence_weight=0.60, color="yellow"
    ),
    StudyDesign.CROSS_SECTIONAL: StudyDesignInfo(
        code="cross_sectional", label="Cross-sectional Study", short_label="Cross-sec",
        category="Observational", evidence_weight=0.50, color="yellow"
    ),
    StudyDesign.CASE_CONTROL: StudyDesignInfo(
        code="case_control", label="Case-Control Study", short_label="Case-ctrl",
        category="Observational", evidence_weight=0.55, color="yellow"
    ),
    StudyDesign.PANEL: StudyDesignInfo(
        code="panel", label="Panel Study", short_label="Panel",
        category="Observational", evidence_weight=0.55, color="yellow"
    ),
    
    # Qualitative (weight: 0.4 - different kind of evidence)
    StudyDesign.QUALITATIVE: StudyDesignInfo(
        code="qualitative", label="Qualitative Research", short_label="Qualitative",
        category="Qualitative", evidence_weight=0.40, color="purple"
    ),
    StudyDesign.MIXED_METHODS: StudyDesignInfo(
        code="mixed_methods", label="Mixed Methods", short_label="Mixed",
        category="Qualitative", evidence_weight=0.50, color="purple"
    ),
    StudyDesign.CASE_STUDY: StudyDesignInfo(
        code="case_study", label="Case Study", short_label="Case",
        category="Qualitative", evidence_weight=0.35, color="purple"
    ),
    StudyDesign.ETHNOGRAPHY: StudyDesignInfo(
        code="ethnography", label="Ethnography", short_label="Ethno",
        category="Qualitative", evidence_weight=0.35, color="purple"
    ),
    
    # Synthesis (weight: 0.9 - aggregates other evidence)
    StudyDesign.SYSTEMATIC_REVIEW: StudyDesignInfo(
        code="systematic_review", label="Systematic Review", short_label="SR",
        category="Synthesis", evidence_weight=0.90, color="teal"
    ),
    StudyDesign.META_ANALYSIS: StudyDesignInfo(
        code="meta_analysis", label="Meta-Analysis", short_label="Meta",
        category="Synthesis", evidence_weight=0.95, color="teal"
    ),
    
    # Other (weight: 0.2-0.3)
    StudyDesign.MODELING: StudyDesignInfo(
        code="modeling", label="Modeling/Simulation", short_label="Model",
        category="Other", evidence_weight=0.30, color="gray"
    ),
    StudyDesign.DESCRIPTIVE: StudyDesignInfo(
        code="descriptive", label="Descriptive Study", short_label="Desc",
        category="Other", evidence_weight=0.25, color="gray"
    ),
    StudyDesign.THEORY: StudyDesignInfo(
        code="theory", label="Theoretical/Conceptual", short_label="Theory",
        category="Other", evidence_weight=0.20, color="gray"
    ),
    StudyDesign.UNKNOWN: StudyDesignInfo(
        code="unknown", label="Unknown/Not classified", short_label="?",
        category="Other", evidence_weight=0.10, color="gray"
    ),
}


def get_study_design_info(design: StudyDesign) -> StudyDesignInfo:
    """Get display info for a study design."""
    return STUDY_DESIGN_INFO.get(design, STUDY_DESIGN_INFO[StudyDesign.UNKNOWN])


def get_study_designs_by_category() -> Dict[str, List[StudyDesign]]:
    """Group study designs by category for UI dropdowns."""
    categories: Dict[str, List[StudyDesign]] = {}
    for design, info in STUDY_DESIGN_INFO.items():
        if info.category not in categories:
            categories[info.category] = []
        categories[info.category].append(design)
    return categories


def parse_study_design(value: Optional[str]) -> StudyDesign:
    """Parse a string value into a StudyDesign enum."""
    if not value:
        return StudyDesign.UNKNOWN
    
    value_lower = value.lower().strip()
    
    # Try exact match
    for design in StudyDesign:
        if design.value == value_lower:
            return design
    
    # Try fuzzy matching
    keyword_map = {
        "rct": StudyDesign.RCT,
        "randomized": StudyDesign.RCT,
        "randomised": StudyDesign.RCT,
        "cluster": StudyDesign.CLUSTER_RCT,
        "rdd": StudyDesign.REGRESSION_DISCONTINUITY,
        "discontinuity": StudyDesign.REGRESSION_DISCONTINUITY,
        "did": StudyDesign.DIFFERENCE_IN_DIFFERENCES,
        "diff-in-diff": StudyDesign.DIFFERENCE_IN_DIFFERENCES,
        "difference": StudyDesign.DIFFERENCE_IN_DIFFERENCES,
        "iv": StudyDesign.INSTRUMENTAL_VARIABLE,
        "instrumental": StudyDesign.INSTRUMENTAL_VARIABLE,
        "psm": StudyDesign.PROPENSITY_SCORE_MATCHING,
        "propensity": StudyDesign.PROPENSITY_SCORE_MATCHING,
        "matching": StudyDesign.PROPENSITY_SCORE_MATCHING,
        "its": StudyDesign.INTERRUPTED_TIME_SERIES,
        "interrupted": StudyDesign.INTERRUPTED_TIME_SERIES,
        "synthetic": StudyDesign.SYNTHETIC_CONTROL,
        "cohort": StudyDesign.COHORT,
        "cross-sectional": StudyDesign.CROSS_SECTIONAL,
        "cross sectional": StudyDesign.CROSS_SECTIONAL,
        "case-control": StudyDesign.CASE_CONTROL,
        "panel": StudyDesign.PANEL,
        "qualitative": StudyDesign.QUALITATIVE,
        "interview": StudyDesign.QUALITATIVE,
        "focus group": StudyDesign.QUALITATIVE,
        "mixed": StudyDesign.MIXED_METHODS,
        "case study": StudyDesign.CASE_STUDY,
        "ethnograph": StudyDesign.ETHNOGRAPHY,
        "systematic": StudyDesign.SYSTEMATIC_REVIEW,
        "meta-analysis": StudyDesign.META_ANALYSIS,
        "meta analysis": StudyDesign.META_ANALYSIS,
        "simulation": StudyDesign.MODELING,
        "model": StudyDesign.MODELING,
        "descriptive": StudyDesign.DESCRIPTIVE,
        "theory": StudyDesign.THEORY,
        "conceptual": StudyDesign.THEORY,
    }
    
    for keyword, design in keyword_map.items():
        if keyword in value_lower:
            return design
    
    return StudyDesign.UNKNOWN


# Classification prompt for LLM
STUDY_DESIGN_CLASSIFICATION_PROMPT = """Analyze this research document and classify its primary study design.

DOCUMENT TITLE: {title}
ABSTRACT/CONTENT:
{abstract}

STUDY DESIGN CATEGORIES:

EXPERIMENTAL (randomized assignment):
- RCT: Randomized Controlled Trial - random assignment to treatment/control
- CLUSTER_RCT: Cluster RCT - randomization at group/community level

QUASI-EXPERIMENTAL (exploits natural variation):
- REGRESSION_DISCONTINUITY: Uses a cutoff/threshold for assignment
- DIFFERENCE_IN_DIFFERENCES: Compares before/after with treatment/control groups
- INSTRUMENTAL_VARIABLE: Uses exogenous variation to identify causal effects
- PROPENSITY_SCORE_MATCHING: Statistically matches treatment/control groups
- INTERRUPTED_TIME_SERIES: Analyzes trend changes after intervention
- SYNTHETIC_CONTROL: Constructs synthetic counterfactual from donor pool

OBSERVATIONAL (no experimental manipulation):
- COHORT: Follows groups over time
- CROSS_SECTIONAL: Point-in-time measurement
- CASE_CONTROL: Compares cases with controls retrospectively
- PANEL: Repeated observations of same units over time

QUALITATIVE (non-numerical analysis):
- QUALITATIVE: Interviews, focus groups, thematic analysis
- MIXED_METHODS: Combines quantitative and qualitative approaches
- CASE_STUDY: In-depth analysis of specific case(s)
- ETHNOGRAPHY: Immersive observation of communities/cultures

SYNTHESIS:
- SYSTEMATIC_REVIEW: Systematic literature review
- META_ANALYSIS: Statistical synthesis of multiple studies

OTHER:
- MODELING: Simulations, economic modeling, theoretical models
- DESCRIPTIVE: Describes patterns without causal claims
- THEORY: Theoretical/conceptual paper

Return JSON:
{{
    "study_design": "one of the codes above (e.g., 'rct', 'difference_in_differences', 'qualitative')",
    "confidence": 0.0-1.0,
    "evidence_snippets": ["quote from text supporting classification", "..."],
    "reasoning": "Brief explanation of why this classification"
}}

If you cannot determine the study design, return {{"study_design": "unknown", "confidence": 0.0, "evidence_snippets": [], "reasoning": "Could not determine study design"}}
"""


def get_classification_prompt(title: str, abstract: str) -> str:
    """Build the classification prompt for a document."""
    return STUDY_DESIGN_CLASSIFICATION_PROMPT.format(
        title=title or "Unknown",
        abstract=abstract[:4000] if abstract else "No abstract available"
    )
