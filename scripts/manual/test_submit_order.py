import os
import requests
from dotenv import load_dotenv

load_dotenv()

key = os.getenv('PESAPAL_CONSUMER_KEY')
secret = os.getenv('PESAPAL_CONSUMER_SECRET')
# Use Sandbox URL
base_url = "https://pay.pesapal.com/v3/api"

# 1. Get Token
url = f"{base_url}/Auth/RequestToken"
headers = {"Accept": "application/json", "Content-Type": "application/json"}
payload = {"consumer_key": key, "consumer_secret": secret}

try:
    res = requests.post(url, json=payload, headers=headers)
    res.raise_for_status()
    print("Auth Response:", res.json())
    token = res.json().get("token", "")
except Exception as e:
    print("Auth failed:", str(e))
    if hasattr(e, 'response') and e.response is not None:
        print(e.response.text)
    exit(1)

# 2. Register IPN
ipn_url = f"{base_url}/URLSetup/RegisterIPN"
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
ipn_payload = {
    "url": "https://api-gatewayubuntunow-platform-be-production.up.railway.app/api/v1/payments/payment/webhook/pesapal/",
    "ipn_notification_type": "POST"
}

try:
    res = requests.post(ipn_url, json=ipn_payload, headers=headers)
    res.raise_for_status()
    ipn_id = res.json().get("ipn_id")
    print(f"IPN Registered: {ipn_id}")
except Exception as e:
    print("IPN Registration failed:", str(e))
    if hasattr(e, 'response') and e.response is not None:
        print(e.response.text)
    exit(1)

# 3. Submit Order
submit_url = f"{base_url}/Transactions/SubmitOrderRequest"
order_payload = {
    "id": "test-payment-1234",
    "currency": "RWF",
    "amount": 40000,
    "description": "Test Payment",
    "callback_url": "https://dev.ubuntunow.rw/checkout/callback",
    "notification_id": ipn_id,
    "billing_address": {
        "email_address": "test@example.com",
        "phone_number": "",
        "country_code": "RW",
        "first_name": "Test",
        "middle_name": "",
        "last_name": "User",
        "line_1": "",
        "line_2": "",
        "city": "",
        "state": "",
        "postal_code": "",
        "zip_code": ""
    }
}

try:
    res = requests.post(submit_url, json=order_payload, headers=headers)
    res.raise_for_status()
    print("Order Submitted successfully!")
    print(res.json())
except Exception as e:
    print("Submit Order failed:", str(e))
    if hasattr(e, 'response') and e.response is not None:
        print(e.response.text)
    exit(1)
