import requests
import json
import time

API_URL = "https://3iechat.up.railway.app/admin/jobs/trigger"

def trigger_processing():
    print(f"Triggering processing via {API_URL}...")
    try:
        # Trigger processing for up to 20 documents
        payload = {
            "force_reprocess": False,
            "max_documents": 20
        }
        
        response = requests.post(API_URL, json=payload)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("\n✅ Trigger successful! Modal should be processing now.")
            print("Waiting 30 seconds to check status...")
            time.sleep(30)
            
            # Check status
            status_url = "https://3iechat.up.railway.app/admin/jobs"
            resp = requests.get(status_url)
            data = resp.json()
            print(f"\nUpdated Status: Queued={data.get('queued_count')}, Processing={data.get('processing_count')}")
            
    except Exception as e:
        print(f"Error triggering processing: {e}")

if __name__ == "__main__":
    trigger_processing()
