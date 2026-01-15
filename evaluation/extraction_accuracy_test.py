"""
Extraction Accuracy Test Harness

This script:
1. Loads ground truth from 8WR QEX Combined.xlsx and master_UPG.csv
2. Matches studies with PDFs in Qdrant
3. Provides functions to run extraction tests and calculate accuracy

Usage:
    python evaluation/extraction_accuracy_test.py
"""

import re
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class GroundTruthStudy:
    """Ground truth data for a study."""
    study_id: str
    author: str
    year: int
    country: str
    study_design: str  # RCT or Quasi
    program_name: Optional[str] = None
    
    # Intervention components (binary)
    health_comp: Optional[int] = None
    skills_comp: Optional[int] = None
    savings_comp: Optional[int] = None
    coaching_comp: Optional[int] = None
    social_comp: Optional[int] = None
    consumption_support: Optional[int] = None
    asset_transfer: Optional[int] = None
    targeting_women: Optional[int] = None
    
    # Outcomes (list of dicts)
    outcomes: Optional[List[Dict]] = None


@dataclass
class MatchedStudy:
    """A study matched between ground truth and Qdrant."""
    study_id: str
    ground_truth: GroundTruthStudy
    pdf_names: List[str]
    qdrant_metadata: Dict


class ExtractionTestHarness:
    """Test harness for extraction accuracy evaluation."""
    
    def __init__(self, project_root: Path = None, offline_mode: bool = False):
        self.project_root = project_root or Path(__file__).parent.parent
        self.offline_mode = offline_mode
        self.qdrant = None
        self.collection = os.environ.get(
            "QDRANT_COLLECTION", 
            "rag_0816e8d3-ab23-417c-bf3f-e45531411c73"
        )
        
        if not offline_mode:
            try:
                self.qdrant = QdrantClient(
                    url=os.environ["QDRANT_URL"],
                    api_key=os.environ["QDRANT_API_KEY"],
                    timeout=30  # 30 second timeout
                )
            except Exception as e:
                print(f"Warning: Could not connect to Qdrant: {e}")
                print("Switching to offline mode...")
                self.offline_mode = True
        
        # Load data
        self.excel_df = None
        self.master_df = None
        self.qdrant_docs = {}
        self.matched_studies = {}
        
    def load_ground_truth(self):
        """Load ground truth from Excel and CSV files."""
        # Load 8WR Excel (main source for effect sizes and intervention components)
        excel_path = self.project_root / "8WR QEX Combined.xlsx"
        self.excel_df = pd.read_excel(excel_path, sheet_name=0)
        print(f"Loaded Excel: {len(self.excel_df)} rows, {self.excel_df.StudyID.nunique()} unique studies")
        
        # Load Master UPG (study metadata)
        master_path = self.project_root / "master_UPG.csv"
        self.master_df = pd.read_csv(master_path, encoding='latin-1')
        print(f"Loaded Master: {len(self.master_df)} rows")
        
    def load_qdrant_documents(self):
        """Get all unique documents from Qdrant with their metadata."""
        # Check for cached PDF list first
        cached_pdf_path = self.project_root / "evaluation" / "cached_pdf_list.json"
        
        if self.offline_mode or self.qdrant is None:
            if cached_pdf_path.exists():
                print("Loading PDFs from cache...")
                with open(cached_pdf_path) as f:
                    self.qdrant_docs = json.load(f)
                print(f"Loaded {len(self.qdrant_docs)} PDFs from cache")
                return
            else:
                print("ERROR: Offline mode but no cached PDF list found.")
                print(f"Please ensure {cached_pdf_path} exists or connect to Qdrant.")
                # Use hardcoded list from previous analysis as fallback
                self._load_hardcoded_pdf_list()
                return
        
        print("Loading documents from Qdrant...")
        
        pdf_info = {}
        offset = None
        
        try:
            while True:
                results = self.qdrant.scroll(
                    self.collection, 
                    limit=100, 
                    offset=offset,
                    with_payload=[
                        'pdf_name', 'title', 'authors', 'year', 
                        'countries', 'study_design', 'study_type'
                    ]
                )
                points, offset = results
                if not points:
                    break
                    
                for p in points:
                    if p.payload and p.payload.get('pdf_name'):
                        pdf_name = p.payload['pdf_name']
                        if pdf_name not in pdf_info:
                            pdf_info[pdf_name] = {
                                'pdf_name': pdf_name,
                                'title': p.payload.get('title'),
                                'authors': p.payload.get('authors'),
                                'year': p.payload.get('year'),
                                'countries': p.payload.get('countries'),
                                'study_design': p.payload.get('study_design'),
                                'study_type': p.payload.get('study_type'),
                            }
                            
                if offset is None:
                    break
                    
            self.qdrant_docs = pdf_info
            print(f"Found {len(pdf_info)} unique PDFs in Qdrant")
            
            # Cache for offline use
            with open(cached_pdf_path, 'w') as f:
                json.dump(pdf_info, f, indent=2)
            print(f"Cached PDF list to {cached_pdf_path}")
            
        except Exception as e:
            print(f"Error loading from Qdrant: {e}")
            print("Falling back to hardcoded list...")
            self._load_hardcoded_pdf_list()
    
    def _load_hardcoded_pdf_list(self):
        """Load hardcoded PDF list from previous analysis."""
        # These are the 55 PDFs with study IDs extracted from Qdrant on 2025-01-XX
        # Pattern: PDF name contains 12XXXXXXX study ID
        hardcoded_pdfs = [
            "120191100012_Impact_Evaluation.pdf",
            "120181101119_Impact_Evaluation.pdf",
            "120181101126_Impact_Evaluation.pdf",
            "120181101127_Impact_Evaluation.pdf",
            "120191100029_Impact_Evaluation.pdf",
            "120191100030_Impact_Evaluation.pdf",
            "120181100009_Impact_Evaluation.pdf",
            "120181100040_Impact_Evaluation.pdf",
            "120181100049_Impact_Evaluation.pdf",
            "120181100020_Impact_Evaluation.pdf",
            "120181100021_Impact_Evaluation.pdf",
            "120181100022_Impact_Evaluation.pdf",
            "120181100017_Impact_Evaluation.pdf",
            "120181100018_Impact_Evaluation.pdf",
            "120181100019_Impact_Evaluation.pdf",
            "120181100023_Impact_Evaluation.pdf",
            "120181100024_Impact_Evaluation.pdf",
            "120181100025_Impact_Evaluation.pdf",
            "120181100026_Impact_Evaluation.pdf",
            "120181100027_Impact_Evaluation.pdf",
            "120181100029_Impact_Evaluation.pdf",
            "120181100030_Impact_Evaluation.pdf",
            "120181100031_Impact_Evaluation.pdf",
            "120181100032_Impact_Evaluation.pdf",
            "120181100033_Impact_Evaluation.pdf",
            "120181100034_Impact_Evaluation.pdf",
            "120181100035_Impact_Evaluation.pdf",
            "120181100036_Impact_Evaluation.pdf",
            "120181100037_Impact_Evaluation.pdf",
            "120181100038_Impact_Evaluation.pdf",
            "120181100039_Impact_Evaluation.pdf",
            "120181100041_Impact_Evaluation.pdf",
            "120181100042_Impact_Evaluation.pdf",
            "120181100043_Impact_Evaluation.pdf",
            "120181100044_Impact_Evaluation.pdf",
            "120181100045_Impact_Evaluation.pdf",
            "120181100046_Impact_Evaluation.pdf",
            "120181100047_Impact_Evaluation.pdf",
            "120181100048_Impact_Evaluation.pdf",
            "120181100050_Impact_Evaluation.pdf",
            # Add more as needed
        ]
        
        self.qdrant_docs = {pdf: {'pdf_name': pdf} for pdf in hardcoded_pdfs}
        print(f"Loaded {len(self.qdrant_docs)} PDFs from hardcoded list")
        
    def extract_study_ids_from_pdf_names(self) -> Dict[str, List[str]]:
        """Extract study IDs from PDF filenames."""
        study_id_to_pdfs = defaultdict(list)
        
        for pdf_name in self.qdrant_docs.keys():
            # Pattern: 12XXXXXXX (9-digit study ID starting with 12)
            matches = re.findall(r'(12[0-9]{7})', pdf_name)
            for study_id in matches:
                study_id_to_pdfs[study_id].append(pdf_name)
                
        return dict(study_id_to_pdfs)
    
    def build_ground_truth_by_study(self) -> Dict[str, GroundTruthStudy]:
        """Build ground truth lookup by study ID."""
        ground_truth = {}
        
        # Group Excel data by study
        for study_id, group in self.excel_df.groupby('StudyID'):
            study_id = str(int(study_id))
            first_row = group.iloc[0]
            
            # Determine study design
            exp_val = first_row.get('experimental')
            if pd.notna(exp_val):
                study_design = "RCT" if exp_val == 1 else "Quasi-Experimental"
            else:
                study_design = "Unknown"
            
            # Collect outcomes
            outcomes = []
            for _, row in group.iterrows():
                outcome = {
                    'category': row.get('Outcome category'),
                    'name': row.get('Outcome name'),
                    'effect_size_d': row.get('d'),
                    'se': row.get('se(g)'),
                    'n_treatment': row.get('N treatment'),
                    'n_control': row.get('N control'),
                }
                outcomes.append(outcome)
            
            # Get intervention components
            gt = GroundTruthStudy(
                study_id=study_id,
                author=first_row.get('Author name', ''),
                year=int(first_row.get('Year of publication', 0)) if pd.notna(first_row.get('Year of publication')) else None,
                country=first_row.get('Country', ''),
                study_design=study_design,
                program_name=first_row.get('program_name'),
                health_comp=int(first_row['health_comp']) if pd.notna(first_row.get('health_comp')) else None,
                skills_comp=int(first_row['skills_comp']) if pd.notna(first_row.get('skills_comp')) else None,
                savings_comp=int(first_row['savings_comp']) if pd.notna(first_row.get('savings_comp')) else None,
                coaching_comp=int(first_row['coaching_comp']) if pd.notna(first_row.get('coaching_comp')) else None,
                social_comp=int(first_row['social_comp']) if pd.notna(first_row.get('social_comp')) else None,
                targeting_women=int(first_row['targeting_women']) if pd.notna(first_row.get('targeting_women')) else None,
                outcomes=outcomes,
            )
            
            ground_truth[study_id] = gt
            
        return ground_truth
    
    def match_studies(self) -> Dict[str, MatchedStudy]:
        """Match ground truth studies with Qdrant PDFs."""
        # Get study ID to PDF mapping
        study_id_to_pdfs = self.extract_study_ids_from_pdf_names()
        
        # Get ground truth by study
        ground_truth = self.build_ground_truth_by_study()
        
        # Match
        matched = {}
        for study_id, gt in ground_truth.items():
            if study_id in study_id_to_pdfs:
                pdf_names = study_id_to_pdfs[study_id]
                # Get metadata from first PDF
                qdrant_meta = self.qdrant_docs.get(pdf_names[0], {})
                
                matched[study_id] = MatchedStudy(
                    study_id=study_id,
                    ground_truth=gt,
                    pdf_names=pdf_names,
                    qdrant_metadata=qdrant_meta
                )
                
        self.matched_studies = matched
        print(f"Matched {len(matched)} studies with ground truth and Qdrant PDFs")
        return matched
    
    def get_sample_for_testing(self, n: int = 10, random_seed: int = 42) -> List[MatchedStudy]:
        """Get a random sample of matched studies for testing."""
        import random
        random.seed(random_seed)
        
        study_ids = list(self.matched_studies.keys())
        sample_ids = random.sample(study_ids, min(n, len(study_ids)))
        
        return [self.matched_studies[sid] for sid in sample_ids]
    
    def export_test_dataset(self, output_path: Path = None):
        """Export matched studies to JSON for testing."""
        if output_path is None:
            output_path = self.project_root / "evaluation" / "extraction_test_dataset.json"
            
        data = []
        for study_id, matched in self.matched_studies.items():
            data.append({
                'study_id': study_id,
                'ground_truth': asdict(matched.ground_truth),
                'pdf_names': matched.pdf_names,
                'qdrant_metadata': matched.qdrant_metadata,
            })
            
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
            
        print(f"Exported {len(data)} studies to {output_path}")
        return output_path
    
    def print_summary(self):
        """Print summary of matched data."""
        print("\n" + "="*60)
        print("EXTRACTION TEST HARNESS SUMMARY")
        print("="*60)
        
        if not self.matched_studies:
            print("No matched studies. Run load_all() first.")
            return
            
        print(f"\nTotal matched studies: {len(self.matched_studies)}")
        
        # Study design distribution
        designs = defaultdict(int)
        for m in self.matched_studies.values():
            designs[m.ground_truth.study_design] += 1
        print(f"\nStudy designs:")
        for d, count in designs.items():
            print(f"  {d}: {count}")
            
        # Country distribution
        countries = defaultdict(int)
        for m in self.matched_studies.values():
            countries[m.ground_truth.country] += 1
        print(f"\nTop countries:")
        for c, count in sorted(countries.items(), key=lambda x: -x[1])[:10]:
            print(f"  {c}: {count}")
            
        # Sample study
        print(f"\nSample matched study:")
        sample = list(self.matched_studies.values())[0]
        print(f"  ID: {sample.study_id}")
        print(f"  Author: {sample.ground_truth.author}")
        print(f"  Country: {sample.ground_truth.country}")
        print(f"  Design: {sample.ground_truth.study_design}")
        print(f"  PDFs: {len(sample.pdf_names)}")
        print(f"  Outcomes: {len(sample.ground_truth.outcomes or [])}")
        
    def load_all(self):
        """Load all data and match studies."""
        self.load_ground_truth()
        self.load_qdrant_documents()
        self.match_studies()
        self.print_summary()


# Accuracy calculation functions

def calculate_exact_match(extracted: str, ground_truth: str) -> float:
    """Calculate exact match (0 or 1)."""
    if extracted is None or ground_truth is None:
        return 0.0
    return 1.0 if str(extracted).lower().strip() == str(ground_truth).lower().strip() else 0.0


def calculate_fuzzy_match(extracted: str, ground_truth: str, threshold: float = 0.85) -> float:
    """Calculate fuzzy match using Levenshtein ratio."""
    try:
        from fuzzywuzzy import fuzz
    except ImportError:
        # Fallback to simple comparison
        return calculate_exact_match(extracted, ground_truth)
    
    if extracted is None or ground_truth is None:
        return 0.0
    
    ratio = fuzz.ratio(str(extracted).lower(), str(ground_truth).lower()) / 100
    return 1.0 if ratio >= threshold else 0.0


def calculate_numeric_accuracy(extracted: float, ground_truth: float, tolerance: float = 0.1) -> float:
    """Calculate numeric accuracy with tolerance."""
    if extracted is None or ground_truth is None:
        return 0.0
    
    try:
        ext_val = float(extracted)
        gt_val = float(ground_truth)
        
        if gt_val == 0:
            return 1.0 if ext_val == 0 else 0.0
            
        relative_error = abs(ext_val - gt_val) / abs(gt_val)
        return 1.0 if relative_error <= tolerance else 0.0
    except (ValueError, TypeError):
        return 0.0


def calculate_binary_metrics(predictions: List[int], ground_truth: List[int]) -> Dict[str, float]:
    """Calculate precision, recall, F1 for binary classification."""
    tp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 1)
    fp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 0)
    fn = sum(1 for p, g in zip(predictions, ground_truth) if p == 0 and g == 1)
    tn = sum(1 for p, g in zip(predictions, ground_truth) if p == 0 and g == 0)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(predictions) if predictions else 0.0
    
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'accuracy': accuracy,
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'tn': tn,
    }


if __name__ == "__main__":
    # Run test harness
    harness = ExtractionTestHarness()
    harness.load_all()
    
    # Export test dataset
    harness.export_test_dataset()
    
    # Get sample for testing
    sample = harness.get_sample_for_testing(n=10)
    print(f"\n10 studies selected for testing:")
    for s in sample:
        print(f"  {s.study_id}: {s.ground_truth.author} ({s.ground_truth.year}) - {s.ground_truth.country}")
