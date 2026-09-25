import hashlib
import requests
import logging
from datetime import datetime, timezone
from django.conf import settings

logger = logging.getLogger(__name__)

class PesapalService:
    def __init__(self):
        self.env = getattr(settings, 'PESAPAL_ENV', 'sandbox').lower()
        self.consumer_key = getattr(settings, 'PESAPAL_CONSUMER_KEY', None)
        self.consumer_secret = getattr(settings, 'PESAPAL_CONSUMER_SECRET', None)
        
        if self.env == 'sandbox':
            self.base_url = "https://cybqa.pesapal.com/pesapalv3/api"
        else:
            self.base_url = "https://pay.pesapal.com/v3/api"

    def get_access_token(self):
        """
        Retrieves a valid Bearer token from Pesapal.
        """
        if not self.consumer_key or not self.consumer_secret:
            raise ValueError("PESAPAL_CONSUMER_KEY or PESAPAL_CONSUMER_SECRET is not configured.")

        url = f"{self.base_url}/Auth/RequestToken"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "consumer_key": self.consumer_key,
            "consumer_secret": self.consumer_secret
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("error"):
                raise Exception(f"Pesapal Error: {data['error'].get('message', data['error'].get('code'))}")
                
            return data.get("token")
        except requests.exceptions.RequestException as e:
            logger.error(f"Pesapal Auth Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response Body: {e.response.text}")
            raise Exception("Failed to authenticate with Pesapal")

    def register_ipn(self):
        """
        Registers the IPN (Webhook) URL with Pesapal so they can notify us of payment status changes.
        """
        token = self.get_access_token()
        url = f"{self.base_url}/URLSetup/RegisterIPN"
        
        # Determine the backend URL dynamically
        backend_url = getattr(settings, 'BACKEND_URL', 'https://api-gatewayubuntunow-platform-be-production.up.railway.app').rstrip('/')
        
        # The webhook endpoint we will create in Step 4
        ipn_notification_url = f"{backend_url}/api/v1/payments/payment/webhook/pesapal/"

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        payload = {
            "url": ipn_notification_url,
            "ipn_notification_type": "POST"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("error"):
                raise Exception(f"Pesapal Error: {data['error'].get('message', data['error'].get('code'))}")
                
            # Returns an ipn_id that we must pass when submitting orders
            return data.get("ipn_id")
        except requests.exceptions.RequestException as e:
            logger.error(f"Pesapal IPN Registration Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response Body: {e.response.text}")
            raise Exception("Failed to register IPN with Pesapal")

    def submit_order(self, payment, order_data, user):
        """
        Submits an order to Pesapal and returns the redirect_url for the payment iframe
        along with the OrderTrackingId.
        """
        token = self.get_access_token()
        url = f"{self.base_url}/Transactions/SubmitOrderRequest"
        
        # We need an IPN ID. We could register one, or assume one was stored.
        # For this setup, we'll quickly register the IPN to ensure it's always valid.
        ipn_id = self.register_ipn()
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://dev.ubuntunow.rw').rstrip('/')
        callback_url = f"{frontend_url}/checkout/callback" # We'll direct back to the frontend

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        # Build payload according to Pesapal v3 specs
        payload = {
            "id": f"{payment.id}-{payment.order_id}",
            "currency": "RWF",
            "amount": float(payment.payment_amount),
            "description": f"Payment for Order #{payment.order_id}",
            "callback_url": callback_url,
            "notification_id": ipn_id,
            "billing_address": {
                "email_address": getattr(user, 'email', 'customer@ubuntunow.rw'),
                "phone_number": getattr(user, 'phone_number', ''),
                "country_code": "RW",
                "first_name": getattr(user, 'first_name', '') or 'Customer',
                "middle_name": "",
                "last_name": getattr(user, 'last_name', '') or 'User',
                "line_1": order_data.get('delivery_address', {}).get('address_line1', ''),
                "line_2": "",
                "city": order_data.get('delivery_address', {}).get('city', ''),
                "state": "",
                "postal_code": "",
                "zip_code": ""
            }
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get("error"):
                raise Exception(f"Pesapal Error: {data['error'].get('message', data['error'].get('code'))}")
                
            # The API returns 'order_tracking_id' and 'redirect_url'
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Pesapal Submit Order Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response Body: {e.response.text}")
            raise Exception("Failed to submit order to Pesapal")

    def get_transaction_status(self, order_tracking_id):
        """
        Retrieves the actual payment status from Pesapal securely using the OrderTrackingId.
        Returns the payment status (e.g. 'COMPLETED', 'FAILED', 'INVALID').
        """
        token = self.get_access_token()
        url = f"{self.base_url}/Transactions/GetTransactionStatus?orderTrackingId={order_tracking_id}"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Pesapal Get Status Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response Body: {e.response.text}")
            raise Exception("Failed to retrieve transaction status from Pesapal")

pesapal_service = PesapalService()


class IntouchPayService:
    """
    Handles MTN MoMo / Airtel Money push payments via IntouchPay.
    Docs: API Reference > Authentication, API Reference > Request a Payment.
    """

    def __init__(self):
        self.env = getattr(settings, 'INTOUCH_ENV', 'sandbox').lower()
        self.username = getattr(settings, 'INTOUCH_USERNAME', None)
        self.account_no = getattr(settings, 'INTOUCH_ACCOUNT_NO', None)
        self.partner_password = getattr(settings, 'INTOUCH_PARTNER_PASSWORD', None)
        self.callback_url = getattr(settings, 'INTOUCH_CALLBACK_URL', None)

        if self.env == 'sandbox':
            self.base_url = "https://developer.intouchpay.co.rw/api/v1/sandbox"
        else:
            self.base_url = "https://www.intouchpay.co.rw/api"

    def _get_timestamp(self):
        # Required format: YYYYMMDDHHmmss (UTC)
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    def _hash_password(self, timestamp):
        if not (self.username and self.account_no and self.partner_password):
            raise ValueError("INTOUCH_USERNAME, INTOUCH_ACCOUNT_NO or INTOUCH_PARTNER_PASSWORD is not configured.")
        raw = f"{self.username}{self.account_no}{self.partner_password}{timestamp}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _auth_fields(self):
        timestamp = self._get_timestamp()
        return {
            "username": self.username,
            "accountno": self.account_no,
            "timestamp": timestamp,
            "password": self._hash_password(timestamp),
        }

    def request_payment(self, amount, mobile_phone, request_transaction_id):
        """
        Triggers a MoMo/Airtel push prompt on the payer's phone.
        Returns the raw IntouchPay response (a 'Pending' request acknowledgement
        only - the final payment status arrives later via the webhook callback).
        """
        url = f"{self.base_url}/requestpayment/"
        payload = {
            **self._auth_fields(),
            "amount": float(amount),
            "mobilephone": mobile_phone,
            "requesttransactionid": request_transaction_id,
            "callbackurl": self.callback_url,
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
        except requests.exceptions.RequestException as e:
            logger.error(f"IntouchPay Request Payment Error: {e}")
            raise Exception("Failed to reach IntouchPay")

        # IntouchPay returns structured error JSON (success/responsecode/message)
        # even on non-2xx statuses (e.g. 404 for "No such user") - parse it
        # instead of treating the status code as a hard failure.
        try:
            return response.json()
        except ValueError:
            logger.error(f"IntouchPay Request Payment Error: HTTP {response.status_code} - {response.text}")
            raise Exception("Failed to request payment from IntouchPay")

    def get_transaction_status(self, request_transaction_id, transaction_id):
        """
        Manual reconciliation fallback for when a webhook callback is missed.
        Not used in the normal payment flow - the webhook is the source of truth.
        """
        url = f"{self.base_url}/gettransactionstatus/"
        payload = {
            **self._auth_fields(),
            "requesttransactionid": request_transaction_id,
            "transactionid": transaction_id,
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
        except requests.exceptions.RequestException as e:
            logger.error(f"IntouchPay Get Transaction Status Error: {e}")
            raise Exception("Failed to reach IntouchPay")

        try:
            return response.json()
        except ValueError:
            logger.error(f"IntouchPay Get Transaction Status Error: HTTP {response.status_code} - {response.text}")
            raise Exception("Failed to retrieve transaction status from IntouchPay")

    def send_deposit(self, amount, mobile_phone, request_transaction_id, reason, withdraw_charge=0, sid=1):
        """
        B2C push - disburses funds directly to a mobile money wallet, no
        approval needed. Not yet wired into any view; intended for the
        escrow "release to seller" step once seller payout numbers exist.
        """
        url = f"{self.base_url}/requestdeposit/"
        payload = {
            **self._auth_fields(),
            "amount": float(amount),
            "mobilephone": mobile_phone,
            "requesttransactionid": request_transaction_id,
            "callbackurl": self.callback_url,
            "reason": reason,
            "withdrawcharge": withdraw_charge,
            "sid": sid,
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
        except requests.exceptions.RequestException as e:
            logger.error(f"IntouchPay Send Deposit Error: {e}")
            raise Exception("Failed to reach IntouchPay")

        try:
            return response.json()
        except ValueError:
            logger.error(f"IntouchPay Send Deposit Error: HTTP {response.status_code} - {response.text}")
            raise Exception("Failed to send deposit via IntouchPay")

    def get_balance(self):
        """
        Live balance of the IntouchPay merchant account (sandbox or
        production, depending on INTOUCH_ENV). Used by the admin dashboard.
        """
        url = f"{self.base_url}/getbalance/"
        payload = self._auth_fields()
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
        except requests.exceptions.RequestException as e:
            logger.error(f"IntouchPay Get Balance Error: {e}")
            raise Exception("Failed to reach IntouchPay")

        try:
            return response.json()
        except ValueError:
            logger.error(f"IntouchPay Get Balance Error: HTTP {response.status_code} - {response.text}")
            raise Exception("Failed to retrieve balance from IntouchPay")


intouch_service = IntouchPayService()
