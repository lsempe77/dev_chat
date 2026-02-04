-- Extracted Estimates Table
-- Stores effect sizes and treatment effects extracted from study PDFs
-- Used by the chatbot for quantitative evidence synthesis

-- =============================================================================
-- Extracted Estimates Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS extracted_estimates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Study identification
    study_id TEXT NOT NULL,  -- Links to document/study identifier
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,  -- Optional: link to documents table
    rag_project_id UUID REFERENCES rag_projects(id) ON DELETE CASCADE,  -- For RLS
    
    -- Source table info
    table_number TEXT,  -- e.g., "Table2", "Table A1"
    table_caption TEXT,
    page_number INTEGER,
    pdf_name TEXT,
    
    -- Effect identification
    treatment_arm TEXT NOT NULL,  -- e.g., "Treatment", "Cash + Training"
    outcome_name TEXT NOT NULL,  -- e.g., "Income", "Food expenditure"
    outcome_category TEXT,  -- e.g., "Income", "Assets", "Health"
    
    -- Primary effect statistics
    coefficient DOUBLE PRECISION,  -- Point estimate
    standard_error DOUBLE PRECISION,
    p_value DOUBLE PRECISION,
    ci_lower DOUBLE PRECISION,  -- 95% CI lower bound
    ci_upper DOUBLE PRECISION,  -- 95% CI upper bound
    
    -- Sample sizes
    sample_size INTEGER,  -- Total N
    n_treatment INTEGER,
    n_control INTEGER,
    
    -- Control group statistics (for effect size calculation)
    control_mean DOUBLE PRECISION,
    control_sd DOUBLE PRECISION,
    
    -- Standardized effect sizes
    cohens_d DOUBLE PRECISION,
    hedges_g DOUBLE PRECISION,
    effect_size_assumption TEXT,  -- How effect size was calculated
    
    -- Effect classification
    is_main_effect BOOLEAN DEFAULT true,
    is_subgroup BOOLEAN DEFAULT false,
    subgroup_variable TEXT,  -- e.g., "Gender", "Region"
    
    -- Study metadata (denormalized for query performance)
    authors TEXT,
    year INTEGER,
    country TEXT,
    study_design TEXT,  -- e.g., "RCT", "DiD", "RDD"
    
    -- Extraction metadata
    extraction_confidence DOUBLE PRECISION,  -- LLM confidence score
    extraction_method TEXT DEFAULT 'pipeline',  -- 'pipeline', 'manual', 'llm_prose'
    extraction_version TEXT,  -- Version of extraction pipeline
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Natural language description for chatbot context
    -- Generated summary of this effect for use in RAG responses
    effect_summary TEXT GENERATED ALWAYS AS (
        COALESCE(treatment_arm, 'Treatment') || ' effect on ' || 
        COALESCE(outcome_name, 'outcome') || ': ' ||
        COALESCE(coefficient::TEXT, 'N/A') ||
        CASE WHEN standard_error IS NOT NULL THEN ' (SE: ' || standard_error::TEXT || ')' ELSE '' END ||
        CASE WHEN p_value IS NOT NULL THEN ', p=' || p_value::TEXT ELSE '' END ||
        CASE WHEN cohens_d IS NOT NULL THEN ', d=' || ROUND(cohens_d::NUMERIC, 3)::TEXT ELSE '' END
    ) STORED
);

-- =============================================================================
-- Indexes for Performance
-- =============================================================================

-- Fast lookups by study
CREATE INDEX IF NOT EXISTS idx_extracted_estimates_study_id ON extracted_estimates(study_id);
CREATE INDEX IF NOT EXISTS idx_extracted_estimates_document_id ON extracted_estimates(document_id);
CREATE INDEX IF NOT EXISTS idx_extracted_estimates_rag_project_id ON extracted_estimates(rag_project_id);

-- Query by outcome category for aggregation
CREATE INDEX IF NOT EXISTS idx_extracted_estimates_outcome_category ON extracted_estimates(outcome_category);

-- Filter by country/study design
CREATE INDEX IF NOT EXISTS idx_extracted_estimates_country ON extracted_estimates(country);
CREATE INDEX IF NOT EXISTS idx_extracted_estimates_study_design ON extracted_estimates(study_design);

-- Filter main effects vs subgroups
CREATE INDEX IF NOT EXISTS idx_extracted_estimates_is_main_effect ON extracted_estimates(is_main_effect) WHERE is_main_effect = true;

-- Full-text search on outcome names
CREATE INDEX IF NOT EXISTS idx_extracted_estimates_outcome_name_trgm 
    ON extracted_estimates USING gin (outcome_name gin_trgm_ops);

-- =============================================================================
-- Row Level Security (RLS) Policies
-- =============================================================================

ALTER TABLE extracted_estimates ENABLE ROW LEVEL SECURITY;

-- Users can view estimates in their projects
CREATE POLICY "Users can view estimates in own projects"
    ON extracted_estimates FOR SELECT
    USING (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
        OR rag_project_id IS NULL  -- Allow viewing unassigned estimates (admin data)
    );

-- Users can insert estimates in their projects
CREATE POLICY "Users can insert estimates in own projects"
    ON extracted_estimates FOR INSERT
    WITH CHECK (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
        OR rag_project_id IS NULL
    );

-- Users can update estimates in their projects
CREATE POLICY "Users can update estimates in own projects"
    ON extracted_estimates FOR UPDATE
    USING (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
    );

-- Users can delete estimates in their projects
CREATE POLICY "Users can delete estimates in own projects"
    ON extracted_estimates FOR DELETE
    USING (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
    );

-- =============================================================================
-- Trigger for updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_extracted_estimates_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_extracted_estimates_updated_at
    BEFORE UPDATE ON extracted_estimates
    FOR EACH ROW
    EXECUTE FUNCTION update_extracted_estimates_updated_at();

-- =============================================================================
-- Utility Views
-- =============================================================================

-- View for aggregated study-level statistics (useful for chatbot)
CREATE OR REPLACE VIEW study_effect_summary AS
SELECT 
    study_id,
    authors,
    year,
    country,
    study_design,
    COUNT(*) AS total_effects,
    COUNT(DISTINCT outcome_category) AS outcome_categories,
    COUNT(*) FILTER (WHERE is_main_effect) AS main_effects,
    AVG(cohens_d) FILTER (WHERE cohens_d IS NOT NULL) AS avg_cohens_d,
    AVG(hedges_g) FILTER (WHERE hedges_g IS NOT NULL) AS avg_hedges_g,
    MIN(p_value) AS min_p_value,
    ARRAY_AGG(DISTINCT outcome_category) FILTER (WHERE outcome_category IS NOT NULL) AS outcome_categories_list
FROM extracted_estimates
GROUP BY study_id, authors, year, country, study_design;

-- View for outcome-level aggregation across studies
CREATE OR REPLACE VIEW outcome_meta_analysis AS
SELECT 
    outcome_category,
    COUNT(DISTINCT study_id) AS n_studies,
    COUNT(*) AS n_estimates,
    AVG(cohens_d) AS pooled_cohens_d,
    STDDEV(cohens_d) AS sd_cohens_d,
    AVG(hedges_g) AS pooled_hedges_g,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cohens_d) AS median_cohens_d
FROM extracted_estimates
WHERE cohens_d IS NOT NULL
GROUP BY outcome_category;

-- =============================================================================
-- Comments for documentation
-- =============================================================================

COMMENT ON TABLE extracted_estimates IS 'Stores effect sizes extracted from study PDFs for quantitative evidence synthesis';
COMMENT ON COLUMN extracted_estimates.effect_summary IS 'Auto-generated natural language summary for chatbot RAG context';
COMMENT ON COLUMN extracted_estimates.extraction_method IS 'How this estimate was extracted: pipeline (automated), manual (human), llm_prose (from narrative)';
COMMENT ON VIEW study_effect_summary IS 'Aggregated statistics per study for quick overview';
COMMENT ON VIEW outcome_meta_analysis IS 'Cross-study aggregation by outcome category for meta-analysis context';
