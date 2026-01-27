# Extraction Pipeline

The `extraction_pipeline/` package handles treatment effect extraction from academic papers.

## Main Pipeline

```{eval-rst}
.. automodule:: extraction_pipeline.pipeline
   :members:
   :undoc-members:
   :show-inheritance:
```

## Usage

```bash
# Extract from specific study
python extraction_pipeline/pipeline.py --study_id 121058356

# Skip LLM classification (faster, rules-only)
python extraction_pipeline/pipeline.py --no-llm

# Skip context enrichment
python extraction_pipeline/pipeline.py --no-enrich
```

## Output Format

Results are saved to `outputs/{study_id}/`:

### extracted_data.csv

| Column | Description |
|--------|-------------|
| `study_id` | Study identifier |
| `table_number` | Table reference (e.g., "Table1") |
| `table_caption` | Full table caption |
| `page_number` | Page where table appears |
| `section` | Section/panel within table |
| `treatment_arm` | Intervention arm name |
| `outcome_name` | Outcome variable |
| `coefficient` | Effect size coefficient |
| `standard_error` | Standard error |
| `significance` | Star notation (*, **, ***) |
| `sample_size` | N for estimate |
| `control_mean` | Control group mean |
| `control_sd` | Control group SD |
| `literal_cell_text` | Raw cell text |
| `outcome_definition` | LLM-enriched definition |

### extracted_data.json

Same data in JSON format for programmatic access.

### metadata.json

```json
{
  "study_id": "121058356",
  "title": "Pathways out of Extreme Poverty",
  "authors": [],
  "year": 2021,
  "page_count": 93,
  "source_key": "path/to/pdf"
}
```
