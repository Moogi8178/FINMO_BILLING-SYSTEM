import logging
from datetime import timedelta

from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Package, Customer, Invoice, Payment
from .serializers import (
    PackageSerializer, CustomerSerializer, InvoiceSerializer,
    PaymentSerializer, InitiatePaymentSerializer,
)
from . import mpesa

logger = logging.getLogger(__name__)


class PackageViewSet(viewsets.ModelViewSet):
    queryset = Package.objects.all()
    serializer_class = PackageSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def initiate_payment(request):
    """
    Trigger an M-Pesa STK Push for a given invoice.
    Body: { "invoice_id": <int> }
    """
    serializer = InitiatePaymentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    invoice_id = serializer.validated_data['invoice_id']

    try:
        invoice = Invoice.objects.select_related('customer').get(id=invoice_id)
    except Invoice.DoesNotExist:
        return Response({"error": "Invoice not found"}, status=status.HTTP_404_NOT_FOUND)

    if invoice.status == 'paid':
        return Response({"error": "Invoice already paid"}, status=status.HTTP_400_BAD_REQUEST)

    payment = Payment.objects.create(
        invoice=invoice,
        phone_number=invoice.customer.phone_number,
        amount=invoice.amount,
        status='initiated',
    )

    try:
        result = mpesa.stk_push(
            phone_number=invoice.customer.phone_number,
            amount=invoice.amount,
            account_reference=invoice.invoice_number,
            description=f"WiFi-{invoice.package.name}",
        )
    except mpesa.MpesaError as e:
        payment.status = 'failed'
        payment.result_desc = str(e)
        payment.save()
        logger.error("STK push failed for invoice %s: %s", invoice.invoice_number, e)
        return Response({"error": "Failed to initiate M-Pesa payment", "detail": str(e)},
                         status=status.HTTP_502_BAD_GATEWAY)

    payment.merchant_request_id = result.get('MerchantRequestID')
    payment.checkout_request_id = result.get('CheckoutRequestID')
    payment.status = 'pending' if result.get('ResponseCode') == '0' else 'failed'
    payment.result_desc = result.get('ResponseDescription', '')
    payment.save()

    return Response({
        "message": "STK push sent. Ask the customer to check their phone and enter their M-Pesa PIN.",
        "payment_id": payment.id,
        "checkout_request_id": payment.checkout_request_id,
    }, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def mpesa_callback(request):
    """
    Safaricom calls this URL after the customer completes (or cancels) the STK prompt.
    This URL must be publicly reachable over HTTPS and set as MPESA_CALLBACK_URL.
    """
    data = request.data
    logger.info("M-Pesa callback received: %s", data)

    try:
        stk_callback = data['Body']['stkCallback']
        checkout_request_id = stk_callback['CheckoutRequestID']
        result_code = stk_callback['ResultCode']
        result_desc = stk_callback.get('ResultDesc', '')
    except (KeyError, TypeError):
        logger.error("Malformed M-Pesa callback payload: %s", data)
        return Response({"ResultCode": 1, "ResultDesc": "Malformed payload"}, status=200)

    try:
        payment = Payment.objects.get(checkout_request_id=checkout_request_id)
    except Payment.DoesNotExist:
        logger.error("No matching payment for CheckoutRequestID %s", checkout_request_id)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"}, status=200)

    payment.result_code = str(result_code)
    payment.result_desc = result_desc

    if result_code == 0:
        # Successful payment - extract receipt details
        items = {i['Name']: i.get('Value') for i in stk_callback['CallbackMetadata']['Item']}
        payment.mpesa_receipt_number = items.get('MpesaReceiptNumber')
        payment.transaction_date = str(items.get('TransactionDate'))
        payment.status = 'completed'
        payment.save()

        # Mark invoice paid and extend customer subscription
        invoice = payment.invoice
        invoice.status = 'paid'
        invoice.paid_at = timezone.now()
        invoice.save()

        customer = invoice.customer
        today = timezone.now().date()
        start = customer.subscription_end if (customer.subscription_end and customer.subscription_end > today) else today
        customer.subscription_start = customer.subscription_start or today
        customer.subscription_end = start + timedelta(days=invoice.package.duration_days)
        customer.status = 'active'
        customer.save()
    else:
        payment.status = 'cancelled' if result_code == 1032 else 'failed'
        payment.save()

    # Safaricom just needs a 200 OK acknowledgement
    return Response({"ResultCode": 0, "ResultDesc": "Accepted"}, status=200)

@api_view(['GET'])
@permission_classes([AllowAny])
def create_superuser_once(request):
    """
    One-time setup endpoint to create an admin user on hosts without shell access
    (e.g. Render's free tier). Protected by a secret token so randoms can't hit it.

    Visit: /api/setup/create-admin/?token=<SETUP_SECRET>
    Set ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD, SETUP_SECRET as env vars first.
    Does nothing (safely) if a superuser already exists or the token is wrong.
    """
    from django.contrib.auth.models import User
    from django.conf import settings as django_settings

    token = request.GET.get('token', '')
    expected_token = getattr(django_settings, 'SETUP_SECRET', '')

    if not expected_token or token != expected_token:
        return Response({"error": "Invalid or missing token"}, status=status.HTTP_403_FORBIDDEN)

    if User.objects.filter(is_superuser=True).exists():
        if request.GET.get('reset') == 'true':
            User.objects.filter(is_superuser=True).delete()
        else:
            return Response({"message": "A superuser already exists. Add &reset=true to the URL to replace it."})

    username = getattr(django_settings, 'ADMIN_USERNAME', '')
    email = getattr(django_settings, 'ADMIN_EMAIL', '')
    password = getattr(django_settings, 'ADMIN_PASSWORD', '')

    if not username or not password:
        return Response(
            {"error": "Set ADMIN_USERNAME and ADMIN_PASSWORD env vars first"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    User.objects.create_superuser(username=username, email=email, password=password)
    return Response({"message": f"Superuser '{username}' created. You can now log in at /admin/."})
@api_view(['GET'])
def dashboard_summary(request):
    """Quick reporting endpoint: revenue, customer counts, overdue invoices."""
    today = timezone.now().date()
    total_revenue = Invoice.objects.filter(status='paid').aggregate(total=Sum('amount'))['total'] or 0
    this_month_revenue = Invoice.objects.filter(
        status='paid', paid_at__year=today.year, paid_at__month=today.month
    ).aggregate(total=Sum('amount'))['total'] or 0

    customer_counts = Customer.objects.aggregate(
        active=Count('id', filter=Q(status='active')),
        suspended=Count('id', filter=Q(status='suspended')),
        expired=Count('id', filter=Q(status='expired')),
        total=Count('id'),
    )

    overdue_invoices = Invoice.objects.filter(status='pending', due_date__lt=today).count()

    return Response({
        "total_revenue": total_revenue,
        "this_month_revenue": this_month_revenue,
        "customers": customer_counts,
        "overdue_invoices": overdue_invoices,
    })
