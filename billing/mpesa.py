"""
Safaricom Daraja API integration - STK Push (Lipa na M-Pesa Online).

Each provider (WiFi/ISP business) has their own M-Pesa credentials, since
their customers pay directly into their own Paybill/Till - money never
passes through this platform's own account. All functions here take a
Provider instance and use its stored credentials rather than one global
set of settings.

Docs: https://developer.safaricom.co.ke/APIs/MpesaExpressSimulate
"""
import base64
import requests
from datetime import datetime
from django.conf import settings


class MpesaError(Exception):
    pass


def get_access_token(provider):
    """Fetch an OAuth access token using this provider's Consumer Key/Secret."""
    url = f"{provider.mpesa_base_url}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(
        url,
        auth=(provider.mpesa_consumer_key, provider.mpesa_consumer_secret),
        timeout=30,
    )
    if response.status_code != 200:
        raise MpesaError(f"Failed to get access token: {response.text}")
    return response.json()['access_token']


def generate_password_and_timestamp(provider):
    """Daraja requires Base64(Shortcode + Passkey + Timestamp)."""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    raw = f"{provider.mpesa_shortcode}{provider.mpesa_passkey}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def normalize_phone(phone: str) -> str:
    """Convert 07XXXXXXXX or +2547XXXXXXXX to 2547XXXXXXXX as Daraja expects."""
    phone = phone.strip().replace(' ', '').replace('+', '')
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    return phone


def stk_push(provider, phone_number: str, amount: int, account_reference: str, description: str):
    """
    Trigger an STK Push prompt on the customer's phone, charged to the
    given provider's own Paybill/Till.

    Returns the Daraja response dict, which includes:
      - MerchantRequestID
      - CheckoutRequestID
      - ResponseCode ('0' means the push was successfully sent to the phone)
    """
    if not provider.mpesa_shortcode or not provider.mpesa_consumer_key:
        raise MpesaError(f"Provider '{provider.business_name}' has no M-Pesa credentials configured")

    access_token = get_access_token(provider)
    password, timestamp = generate_password_and_timestamp(provider)
    phone_number = normalize_phone(phone_number)

    url = f"{provider.mpesa_base_url}/mpesa/stkpush/v1/processrequest"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "BusinessShortCode": provider.mpesa_shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": provider.mpesa_shortcode,
        "PhoneNumber": phone_number,
        "CallBackURL": settings.MPESA_CALLBACK_URL,
        "AccountReference": account_reference[:12],  # Daraja limits this field
        "TransactionDesc": description[:13],
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    data = response.json()
    if response.status_code != 200:
        raise MpesaError(f"STK push failed: {data}")
    return data


def query_stk_status(provider, checkout_request_id: str):
    """Optional: poll Daraja to check the status of a previously initiated STK push."""
    access_token = get_access_token(provider)
    password, timestamp = generate_password_and_timestamp(provider)

    url = f"{provider.mpesa_base_url}/mpesa/stkpushquery/v1/query"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "BusinessShortCode": provider.mpesa_shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    return response.json()
