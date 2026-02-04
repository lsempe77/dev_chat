"""
Effect Size Calculations
========================

Calculate standardized effect sizes with explicit assumptions.

Calculates:
- Cohen's d: Standardized mean difference
- Hedges' g: Bias-corrected SMD (adjusts for small sample bias)
- Variance and SE of effect sizes

All calculations annotate assumptions in output columns.
"""

import math
from typing import Optional, Dict, Any, Tuple
import pandas as pd
from loguru import logger

from ..core.config import ColumnNames


class EffectSizeAssumption:
    """Enumeration of assumptions made during effect size calculation."""
    
    # Sample size assumptions
    EQUAL_SPLIT = "equal_split"  # N split equally between treatment/control
    TREATMENT_ONLY = "treatment_only"  # Only treatment N available
    CONTROL_ONLY = "control_only"  # Only control N available
    
    # SD assumptions
    CONTROL_SD_ONLY = "control_sd_only"  # Using control group SD only
    POOLED_SD = "pooled_sd"  # Using pooled SD
    IMPUTED_SD = "imputed_sd"  # SD was imputed
    
    # Effect type assumptions
    FROM_COEFFICIENT = "from_coefficient"  # SMD from regression coefficient
    FROM_MEANS = "from_means"  # SMD from group means
    
    # Clustering
    UNCLUSTERED = "unclustered"  # Ignoring clustering
    CLUSTER_ADJUSTED = "cluster_adjusted"  # Cluster-adjusted SE


def calculate_cohens_d(
    coefficient: float,
    sd: float,
) -> float:
    """
    Calculate Cohen's d standardized mean difference.
    
    d = coefficient / SD
    
    Args:
        coefficient: Treatment effect (mean difference)
        sd: Standard deviation (typically control group SD)
        
    Returns:
        Cohen's d value
    """
    if sd == 0:
        return float('nan')
    return coefficient / sd


def calculate_hedges_g(
    cohens_d: float,
    n_total: int,
) -> Tuple[float, float]:
    """
    Calculate Hedges' g (bias-corrected SMD) and correction factor J.
    
    Hedges' g = J * Cohen's d
    J = 1 - 3 / (4 * df - 1)  where df = n_total - 2
    
    Args:
        cohens_d: Cohen's d value
        n_total: Total sample size
        
    Returns:
        Tuple of (hedges_g, j_correction_factor)
    """
    if n_total < 3:
        return float('nan'), float('nan')
    
    df = n_total - 2
    j = 1 - 3 / (4 * df - 1)
    hedges_g = j * cohens_d
    
    return hedges_g, j


def calculate_effect_variance(
    effect_size: float,
    n_treatment: int,
    n_control: int,
) -> float:
    """
    Calculate variance of standardized effect size.
    
    V(d) = (n_t + n_c) / (n_t * n_c) + d^2 / (2 * (n_t + n_c))
    
    Args:
        effect_size: Cohen's d or Hedges' g
        n_treatment: Treatment group sample size
        n_control: Control group sample size
        
    Returns:
        Variance of effect size
    """
    if n_treatment == 0 or n_control == 0:
        return float('nan')
    
    n_total = n_treatment + n_control
    
    term1 = n_total / (n_treatment * n_control)
    term2 = effect_size ** 2 / (2 * n_total)
    
    return term1 + term2


def calculate_effect_sizes_for_row(
    row: Dict[str, Any],
    require_minimum_inputs: bool = True,
) -> Dict[str, Any]:
    """
    Calculate effect sizes for a single row with explicit assumption tracking.
    
    Minimum requirements:
    - coefficient (treatment effect)
    - control_sd OR pooled_sd
    - sample_size OR (n_treatment AND n_control)
    
    Args:
        row: Dict with extraction data
        require_minimum_inputs: If True, skip if minimum inputs not met
        
    Returns:
        Dict with calculated fields and assumption annotations
    """
    result = {
        ColumnNames.COHENS_D: None,
        ColumnNames.HEDGES_G: None,
        ColumnNames.EFFECT_VARIANCE: None,
        ColumnNames.EFFECT_SE: None,
        ColumnNames.EFFECT_SIZE_ASSUMPTION: None,
    }
    
    # Get inputs
    coefficient = row.get(ColumnNames.COEFFICIENT)
    control_sd = row.get(ColumnNames.CONTROL_SD)
    sample_size = row.get(ColumnNames.SAMPLE_SIZE)
    n_treatment = row.get(ColumnNames.N_TREATMENT)
    n_control = row.get(ColumnNames.N_CONTROL)
    
    # Check minimum requirements
    if coefficient is None or pd.isna(coefficient):
        return result
    
    if (control_sd is None or pd.isna(control_sd)) and require_minimum_inputs:
        logger.debug(f"Skipping effect size: no SD available")
        return result
    
    # Track assumptions
    assumptions = []
    
    # === SD handling ===
    sd = None
    if control_sd is not None and not pd.isna(control_sd) and control_sd > 0:
        sd = float(control_sd)
        assumptions.append(EffectSizeAssumption.CONTROL_SD_ONLY)
    else:
        # Cannot calculate without SD
        return result
    
    # === Sample size handling ===
    n_t = None
    n_c = None
    n_total = None
    
    # Prefer explicit treatment/control N
    if n_treatment is not None and not pd.isna(n_treatment):
        n_t = int(n_treatment)
    if n_control is not None and not pd.isna(n_control):
        n_c = int(n_control)
    
    # If both available, use them
    if n_t is not None and n_c is not None:
        n_total = n_t + n_c
    elif sample_size is not None and not pd.isna(sample_size):
        n_total = int(sample_size)
        
        # If we have total but not split, assume equal split
        if n_t is None and n_c is None:
            n_t = n_total // 2
            n_c = n_total - n_t
            assumptions.append(EffectSizeAssumption.EQUAL_SPLIT)
        elif n_t is not None:
            n_c = n_total - n_t
        elif n_c is not None:
            n_t = n_total - n_c
    
    # Check if we have enough sample info
    if n_total is None or n_total < 3:
        if require_minimum_inputs:
            logger.debug(f"Skipping effect size: insufficient sample size info")
            return result
        # Continue with what we have, but note the limitation
        n_total = n_total or 100  # Arbitrary fallback
        n_t = n_t or 50
        n_c = n_c or 50
        assumptions.append("sample_size_estimated")
    
    # Add assumption about effect derivation
    assumptions.append(EffectSizeAssumption.FROM_COEFFICIENT)
    
    # Check for clustering (we can't adjust without ICC, but note it)
    n_clusters = row.get(ColumnNames.N_CLUSTERS)
    if n_clusters is not None and not pd.isna(n_clusters):
        assumptions.append(EffectSizeAssumption.UNCLUSTERED)  # Note we're not adjusting
    
    # === Calculate effect sizes ===
    try:
        # Cohen's d
        cohens_d = calculate_cohens_d(float(coefficient), sd)
        result[ColumnNames.COHENS_D] = cohens_d
        
        # Hedges' g
        hedges_g, j_factor = calculate_hedges_g(cohens_d, n_total)
        result[ColumnNames.HEDGES_G] = hedges_g
        
        # Variance (using Hedges' g)
        variance = calculate_effect_variance(hedges_g, n_t, n_c)
        result[ColumnNames.EFFECT_VARIANCE] = variance
        
        # SE
        if variance > 0 and not math.isnan(variance):
            result[ColumnNames.EFFECT_SE] = math.sqrt(variance)
        
        # Store assumptions
        result[ColumnNames.EFFECT_SIZE_ASSUMPTION] = "|".join(assumptions)
        
    except (ValueError, TypeError, ZeroDivisionError) as e:
        logger.debug(f"Effect size calculation error: {e}")
    
    return result


def calculate_effect_sizes(
    df: pd.DataFrame,
    require_minimum_inputs: bool = True,
) -> pd.DataFrame:
    """
    Calculate standardized effect sizes for entire DataFrame.
    
    Adds columns:
    - cohens_d: Cohen's d standardized mean difference
    - hedges_g: Bias-corrected Hedges' g
    - effect_variance: Variance of effect size
    - effect_se: Standard error of effect size
    - effect_size_assumption: Assumptions made (pipe-separated)
    
    Args:
        df: DataFrame with extraction results
        require_minimum_inputs: If True, skip rows without minimum data
        
    Returns:
        DataFrame with added effect size columns
    """
    if df.empty:
        return df
    
    df = df.copy()
    
    # Initialize columns
    df[ColumnNames.COHENS_D] = None
    df[ColumnNames.HEDGES_G] = None
    df[ColumnNames.EFFECT_VARIANCE] = None
    df[ColumnNames.EFFECT_SE] = None
    df[ColumnNames.EFFECT_SIZE_ASSUMPTION] = None
    
    # Calculate for each row
    calculated_count = 0
    skipped_count = 0
    
    for idx, row in df.iterrows():
        result = calculate_effect_sizes_for_row(
            row.to_dict(),
            require_minimum_inputs=require_minimum_inputs,
        )
        
        for col, value in result.items():
            df.at[idx, col] = value
        
        if result[ColumnNames.COHENS_D] is not None:
            calculated_count += 1
        else:
            skipped_count += 1
    
    # Log summary
    logger.info(
        f"Effect sizes: calculated={calculated_count}, skipped={skipped_count} "
        f"(require_minimum={require_minimum_inputs})"
    )
    
    # Log assumption distribution
    if calculated_count > 0:
        assumptions = df[ColumnNames.EFFECT_SIZE_ASSUMPTION].dropna()
        equal_split_count = assumptions.str.contains(EffectSizeAssumption.EQUAL_SPLIT, na=False).sum()
        if equal_split_count > 0:
            logger.info(f"  {equal_split_count} rows used equal sample split assumption")
    
    return df


def summarize_effect_sizes(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Generate summary statistics for calculated effect sizes.
    
    Returns dict with:
    - coverage: % of rows with effect sizes
    - mean_d: Mean Cohen's d
    - median_d: Median Cohen's d
    - mean_g: Mean Hedges' g
    - assumption_breakdown: Dict of assumption counts
    """
    result = {
        "coverage_pct": 0.0,
        "mean_d": None,
        "median_d": None,
        "sd_d": None,
        "mean_g": None,
        "median_g": None,
        "n_calculated": 0,
        "n_skipped": 0,
        "assumption_breakdown": {},
    }
    
    if df.empty or ColumnNames.COHENS_D not in df.columns:
        return result
    
    valid_d = df[ColumnNames.COHENS_D].dropna()
    result["n_calculated"] = len(valid_d)
    result["n_skipped"] = len(df) - len(valid_d)
    result["coverage_pct"] = 100 * len(valid_d) / len(df) if len(df) > 0 else 0
    
    if len(valid_d) > 0:
        result["mean_d"] = valid_d.mean()
        result["median_d"] = valid_d.median()
        result["sd_d"] = valid_d.std()
        
        valid_g = df[ColumnNames.HEDGES_G].dropna()
        if len(valid_g) > 0:
            result["mean_g"] = valid_g.mean()
            result["median_g"] = valid_g.median()
    
    # Assumption breakdown
    if ColumnNames.EFFECT_SIZE_ASSUMPTION in df.columns:
        assumptions = df[ColumnNames.EFFECT_SIZE_ASSUMPTION].dropna()
        for assumption in [
            EffectSizeAssumption.EQUAL_SPLIT,
            EffectSizeAssumption.CONTROL_SD_ONLY,
            EffectSizeAssumption.UNCLUSTERED,
        ]:
            count = assumptions.str.contains(assumption, na=False).sum()
            if count > 0:
                result["assumption_breakdown"][assumption] = count
    
    return result
