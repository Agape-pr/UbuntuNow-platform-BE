import os
import requests
from dotenv import load_dotenv

load_dotenv()

key = os.getenv('PESAPAL_CONSUMER_KEY')
secret = os.getenv('PESAPAL_CONSUMER_SECRET')

if not key or not secret:
    print("Error: Could not find PESAPAL_CONSUMER_KEY or PESAPAL_CONSUMER_SECRET in .env")
    exit(1)

sandbox_url = "https://cybqa.pesapal.com/pesapalv3/api/Auth/RequestToken"
live_url = "https://pay.pesapal.com/v3/api/Auth/RequestToken"

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}
payload = {
    "consumer_key": key,
    "consumer_secret": secret
}

print("Testing Sandbox...")
res_sandbox = requests.post(sandbox_url, json=payload, headers=headers)
if res_sandbox.status_code == 200:
    print("✅ SUCCESS! These are Sandbox credentials.")
    exit(0)
else:
    print(f"Sandbox failed: {res_sandbox.text}")

print("\nTesting Live...")
res_live = requests.post(live_url, json=payload, headers=headers)
if res_live.status_code == 200:
    print("✅ SUCCESS! These are Live credentials.")
    exit(0)
else:
    print(f"Live failed: {res_live.text}")

print("\n❌ Both failed. Please double check that you copied the keys exactly as they appear in the email with no extra spaces.")
