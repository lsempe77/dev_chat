"""
Analyze all significance patterns in the extraction output.
"""

import pandas as pd
import re

df = pd.read_csv("extraction_pipeline/outputs/121058356/extracted_data.csv")

print("SIGNIFICANCE PATTERN ANALYSIS")
print("=" * 60)

# Check for various patterns
cells = df["literal_cell_text"].dropna().tolist()

# Pattern counters
patterns = {
    "***": 0,
    "**": 0,
    "*": 0,
    "†": 0,
    "‡": 0,
    "§": 0,
    "p<": 0,
    "p=": 0,
    "p>": 0,
    "p value": 0,
    "[": 0,  # brackets often have p-values
    "NS": 0,  # not significant
    "n.s.": 0,
}

for cell in cells:
    cell_str = str(cell)
    for pattern in patterns:
        if pattern in cell_str.lower() if pattern in ["p<", "p=", "p>", "p value", "ns", "n.s."] else pattern in cell_str:
            patterns[pattern] += 1

print("\n1. Pattern frequency in cells:")
for pattern, count in sorted(patterns.items(), key=lambda x: -x[1]):
    if count > 0:
        print(f"   '{pattern}': {count}")

# Find cells with explicit p-values
print("\n2. Sample cells with explicit p-values or brackets:")
for cell in cells[:100]:
    cell_str = str(cell).lower()
    if "p<" in cell_str or "p=" in cell_str or "p>" in cell_str:
        print(f"   '{cell}'")

# Check for dagger/cross symbols
print("\n3. Sample cells with special symbols (†, ‡, etc.):")
special_chars = ["†", "‡", "§", "¶", "||", "a", "b", "c"]
for cell in cells:
    cell_str = str(cell)
    for char in ["†", "‡", "§"]:
        if char in cell_str:
            print(f"   '{cell}'")
            break

# Analyze star patterns more closely
print("\n4. Star notation breakdown:")
star_patterns = {
    "*** only": 0,
    "** only": 0,
    "* only": 0,
    "no stars": 0,
}
for cell in cells:
    cell_str = str(cell)
    if "***" in cell_str:
        star_patterns["*** only"] += 1
    elif "**" in cell_str:
        star_patterns["** only"] += 1
    elif "*" in cell_str:
        star_patterns["* only"] += 1
    else:
        star_patterns["no stars"] += 1

for pattern, count in star_patterns.items():
    pct = count / len(cells) * 100
    print(f"   {pattern}: {count} ({pct:.1f}%)")

print("\n5. Sample of non-starred cells:")
for cell in cells:
    if "*" not in str(cell) and "†" not in str(cell):
        print(f"   '{cell}'")
    if sum(1 for c in cells if "*" not in str(c)) > 10:
        break
