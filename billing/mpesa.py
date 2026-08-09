"""
Safaricom Daraja API integration - STK Push (Lipa na M-Pesa Online).

Docs: https://developer.safaricom.co.ke/APIs/MpesaExpressSimulate
"""
import base64
import requests
from datetime import datetime
from django.conf import settings


class MpesaError(Exception):
    pass


def get_access_token():
    """Fetch an OAuth access token using the Consumer Key/Secret."""
    url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(
        url,
        auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
        timeout=30,
    )
    if response.status_code != 200:
        raise MpesaError(f"Failed to get access token: {response.text}")
    return response.json()['access_token']


def generate_password_and_timestamp():
    """Daraja requires Base64(Shortcode + Passkey + Timestamp)."""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def normalize_phone(phone: str) -> str:
    """Convert 07XXXXXXXX or +2547XXXXXXXX to 2547XXXXXXXX as Daraja expects."""
    phone = phone.strip().replace(' ', '').replace('+', '')
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    return phone


def stk_push(phone_number: str, amount: int, account_reference: str, description: str):
    """
    Trigger an STK Push prompt on the customer's phone.

    Returns the Daraja response dict, which includes:
      - MerchantRequestID
      - CheckoutRequestID
      - ResponseCode ('0' means the push was successfully sent to the phone)
    """
    access_token = get_access_token()
    password, timestamp = generate_password_and_timestamp()
    phone_number = normalize_phone(phone_number)

    url = f"{settings.MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": settings.MPESA_SHORTCODE,
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


def query_stk_status(checkout_request_id: str):
    """Optional: poll Daraja to check the status of a previously initiated STK push."""
    access_token = get_access_token()
    password, timestamp = generate_password_and_timestamp()

    url = f"{settings.MPESA_BASE_URL}/mpesa/stkpushquery/v1/query"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    return response.json()
