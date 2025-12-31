import requests
import json

API_URL = "https://3iechat.up.railway.app/admin/jobs"

def check_api():
    print(f"Querying API: {API_URL}")
    try:
        response = requests.get(API_URL)
        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}")
            return

        data = response.json()
        jobs = data.get("jobs", [])
        queued = data.get("queued_count", 0)
        processing = data.get("processing_count", 0)
        completed = data.get("completed_count", 0)
        
        print(f"Jobs Summary: Queued={queued}, Processing={processing}, Completed={completed}")
        
        # Check for the specific missing files
        missing_examples = [
            "11aa6d14_121294813",
            "18c72c7b_121058368",
            "2facbce1_121498842_Spanish"
        ]
        
        print("\nChecking for specific 'missing' files in Jobs response:")
        for target in missing_examples:
            found = False
            for job in jobs:
                if target in job["id"] or target in job["filename"]:
                    print(f"  ✅ Found {target}: {job['id']} (Status: {job['status']})")
                    found = True
                    break
            if not found:
                print(f"  ❌ Missing {target}")

    except Exception as e:
        print(f"Error querying API: {e}")

if __name__ == "__main__":
    check_api()
