# Evaluation

The `evaluation/` package contains tools for testing and validating the RAG pipeline.

## Validation

### Extraction Validation

```{eval-rst}
.. automodule:: evaluation.validate_extraction
   :members:
   :undoc-members:
   :show-inheritance:
```

## Evaluators

### RAGAS Evaluator

```{eval-rst}
.. automodule:: evaluation.ragas_evaluator
   :members:
   :undoc-members:
   :show-inheritance:
```

### MiniCheck Evaluator

```{eval-rst}
.. automodule:: evaluation.minicheck_evaluator
   :members:
   :undoc-members:
   :show-inheritance:
```

### Reliable Evaluator

```{eval-rst}
.. automodule:: evaluation.reliable_evaluator
   :members:
   :undoc-members:
   :show-inheritance:
```

## Analysis Scripts

### Baseline Analysis

```{eval-rst}
.. automodule:: evaluation.analyze_baselines
   :members:
   :undoc-members:
   :show-inheritance:
```

### Mismatch Analysis

```{eval-rst}
.. automodule:: evaluation.analyze_mismatches
   :members:
   :undoc-members:
   :show-inheritance:
```

## Test Runners

### Run RAGAS Evaluation

```{eval-rst}
.. automodule:: evaluation.run_ragas_eval
   :members:
   :undoc-members:
   :show-inheritance:
```

### Run Claim Ledger Evaluation

```{eval-rst}
.. automodule:: evaluation.run_claim_ledger_eval
   :members:
   :undoc-members:
   :show-inheritance:
```

## Usage

```bash
# Validate extraction against ground truth
python evaluation/validate_extraction.py

# Run RAGAS evaluation
python evaluation/run_ragas_eval.py

# Run MiniCheck evaluation
python evaluation/run_claim_ledger_eval.py
```

## Metrics

| Metric | Description | Current | Target |
|--------|-------------|---------|--------|
| Faithfulness | Claims supported by context | 66.47% | 70%+ |
| Citation Recall | Citations found | 98.86% | 70%+ |
| Citation Precision | Citations accurate | 98.86% | 70%+ |
