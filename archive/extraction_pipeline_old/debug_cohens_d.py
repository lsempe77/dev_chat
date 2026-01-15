import json

with open('../evaluation/matched_studies_r2.json') as f:
    studies = json.load(f)

# Look for Gross consumption outcome in GT
gt = studies[0]['ground_truth']
print("=== GT Outcomes with 'consumption' ===")
for o in gt['outcomes']:
    if 'consumption' in o['name'].lower():
        print(f"Name: {o['name']}")
        print(f"Effect size d: {o['effect_size_d']}")
        print(f"SE: {o['se']}")
        print()

# Also check what coefficient/SD would give us the GT d
print("\n=== Reverse Engineering ===")
# From table:
# Followup 1: Capital coef = 0.15, Control mean = 1.95, Control SD = 1.12
# Followup 2: Capital coef = 0.12, Control mean = 1.67, Control SD = 0.99

# What SD would give GT d = 0.0904 with coef = 0.15?
gt_d = 0.0904
coef = 0.15
needed_sd = coef / gt_d
print(f"To get d={gt_d} with coef={coef}, need SD = {needed_sd:.4f}")

# Check if it's using a different normalization
# Maybe pooled SD from control + treatment groups?
# Or standardizing by baseline SD?

# What if they divide coef by control MEAN instead of SD?
d_by_mean = 0.15 / 1.95
print(f"Coef/Control_Mean = 0.15/1.95 = {d_by_mean:.4f}")

# What if using sample size for conversion?
# d = 2 * t / sqrt(n)
# t = coef / SE = 0.15 / 0.05 = 3
t = 0.15 / 0.05
import math
n = 4405
d_from_t = 2 * t / math.sqrt(n)
print(f"d from t-statistic = 2*{t}/sqrt({n}) = {d_from_t:.4f}")

# Check if GT d matches coef/SD for Followup 2 "Full" treatment
# Full coef = 0.25, SD = 0.99
d_full = 0.25 / 0.99
print(f"Full treatment: 0.25/0.99 = {d_full:.4f}")
