"""
COHEN'S D EXTRACTION PIPELINE - STATUS SUMMARY
================================================

RESULTS ACHIEVED:
-----------------
1. Cohen's d Coverage: 208/342 (60.8%) outcomes have Cohen's d
   - t-stat method: 170 (49.7%) 
   - SD method: 38 (11.1%)

2. Comparison with Ground Truth:
   - Total mapped comparisons: 52
   - Close matches (diff < 0.1): 20 (38.5%)
   
3. For EXACT name matches: 16/20 = 80% accuracy!

KEY FINDINGS:
-------------
- t-stat formula (d = 2*t/sqrt(n)) is CORRECT - perfect match for "Gross consumption"
- 4 exact-name mismatches are likely due to:
  * Different followup periods (6 months vs 18 months)
  * Different treatment groups (some studies have multiple arms)
  * Wrong coefficient row extracted

GROUND TRUTH COVERAGE:
----------------------
Study              | GT Outcomes | Our Extracted | With Cohen's d
-------------------|-------------|---------------|---------------
Bossuroy           | 44          | 86            | 60
Misha              | 3           | 44            | 27
Maldonado          | 2           | 41            | 30
Alderman           | 16          | 134           | 63
Banerjee           | 6           | 37            | 28

NEXT STEPS TO IMPROVE:
----------------------
1. Add followup period filtering - prefer 18 months / endline
2. Add treatment arm filtering - identify correct ITT coefficient
3. Better outcome name normalization for matching
4. Debug the 4 exact-name mismatches

METRIC SUMMARY:
---------------
- Outcome Recall (Stage 1): 100% ✓
- Coefficient Extraction (Stage 2): 76.4% ✓
- Cohen's d Coverage: 60.8% ✓
- Cohen's d Accuracy (exact matches): 80% ✓
- Overall GT match rate: 38.5% (need improvement)
"""
