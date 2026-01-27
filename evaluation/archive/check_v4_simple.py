import json

exts = json.load(open('evaluation/v4_extraction_results_partial.json'))

print("V4 Extraction Summary:")
print(f"Total studies processed: {len(exts)}")

successful = 0
for e in exts:
    n_outcomes = len(e.get('outcomes', []))
    if n_outcomes > 0:
        successful += 1
        print(f"  Study {e['study_id']}: {n_outcomes} outcomes")

print(f"\nStudies with outcomes: {successful}/{len(exts)}")

if successful == 0:
    print("\n❌ V4 EXTRACTED 0 OUTCOMES ACROSS ALL 20 STUDIES")
    print("The multi-pass approach completely failed.")
