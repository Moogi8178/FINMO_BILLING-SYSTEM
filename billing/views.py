import logging
from datetime import timedelta

from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Provider, Package, Customer, Invoice, Payment, CommissionRecord
from .serializers import (
    ProviderSerializer, PackageSerializer, CustomerSerializer, InvoiceSerializer,
    PaymentSerializer, InitiatePaymentSerializer,
)
from . import mpesa

logger = logging.getLogger(__name__)


def get_request_provider(request):
    """Returns the Provider linked to the logged-in user, or None."""
    return getattr(request.user, 'provider', None)


class ProviderScopedViewSet(viewsets.ModelViewSet):
    """
    Base class that automatically scopes queries to the logged-in user's
    Provider, so one provider can never see or edit another's data.
    Superusers (platform admin) see everything.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_superuser:
            return qs
        provider = get_request_provider(self.request)
        if provider is None:
            return qs.none()
        return qs.filter(**{self.provider_filter_field: provider})

    def perform_create(self, serializer):
        provider = get_request_provider(self.request)
        if provider is not None:
            serializer.save(**{self.provider_filter_field: provider})
        else:
            serializer.save()


class ProviderViewSet(viewsets.ModelViewSet):
    """A provider can view/edit only their own record. Superusers see all."""
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Provider.objects.all()
        provider = get_request_provider(self.request)
        if provider is None:
            return Provider.objects.none()
        return Provider.objects.filter(id=provider.id)


class PackageViewSet(ProviderScopedViewSet):
    queryset = Package.objects.all()
    serializer_class = PackageSerializer
    provider_filter_field = 'provider'


class CustomerViewSet(ProviderScopedViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    provider_filter_field = 'provider'


class InvoiceViewSet(ProviderScopedViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    provider_filter_field = 'customer__provider'

    def get_queryset(self):
        qs = Invoice.objects.select_related('customer', 'package')
        if self.request.user.is_superuser:
            return qs
        provider = get_request_provider(self.request)
        if provider is None:
            return qs.none()
        return qs.filter(customer__provider=provider)


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Payment.objects.select_related('invoice__customer')
        if self.request.user.is_superuser:
            return qs
        provider = get_request_provider(self.request)
        if provider is None:
            return qs.none()
        return qs.filter(invoice__customer__provider=provider)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """
    Trigger an M-Pesa STK Push for a given invoice, charged to that
    invoice's provider's own Paybill/Till.
    Body: { "invoice_id": <int> }
    """
    serializer = InitiatePaymentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    invoice_id = serializer.validated_data['invoice_id']

    try:
        invoice = Invoice.objects.select_related('customer', 'customer__provider').get(id=invoice_id)
    except Invoice.DoesNotExist:
        return Response({"error": "Invoice not found"}, status=status.HTTP_404_NOT_FOUND)

    # Access control: only the owning provider (or a superuser) may trigger this
    if not request.user.is_superuser:
        provider = get_request_provider(request)
        if provider is None or invoice.customer.provider_id != provider.id:
            return Response({"error": "Not permitted for this invoice"}, status=status.HTTP_403_FORBIDDEN)

    if invoice.status == 'paid':
        return Response({"error": "Invoice already paid"}, status=status.HTTP_400_BAD_REQUEST)

    provider = invoice.customer.provider

    payment = Payment.objects.create(
        invoice=invoice,
        phone_number=invoice.customer.phone_number,
        amount=invoice.amount,
        status='initiated',
    )

    try:
        result = mpesa.stk_push(
            provider=provider,
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
    One shared URL handles every provider - we look up which payment/provider
    this belongs to via CheckoutRequestID.
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
        payment = Payment.objects.select_related('invoice__customer').get(checkout_request_id=checkout_request_id)
    except Payment.DoesNotExist:
        logger.error("No matching payment for CheckoutRequestID %s", checkout_request_id)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"}, status=200)

    payment.result_code = str(result_code)
    payment.result_desc = result_desc

    if result_code == 0:
        items = {i['Name']: i.get('Value') for i in stk_callback['CallbackMetadata']['Item']}
        payment.mpesa_receipt_number = items.get('MpesaReceiptNumber')
        payment.transaction_date = str(items.get('TransactionDate'))
        payment.status = 'completed'
        payment.save()

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

    return Response({"ResultCode": 0, "ResultDesc": "Accepted"}, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    """Quick reporting endpoint: revenue, customer counts, overdue invoices - scoped to the caller's provider."""
    today = timezone.now().date()

    invoices = Invoice.objects.all()
    customers = Customer.objects.all()
    if not request.user.is_superuser:
        provider = get_request_provider(request)
        if provider is None:
            return Response({"error": "No provider linked to this account"}, status=status.HTTP_403_FORBIDDEN)
        invoices = invoices.filter(customer__provider=provider)
        customers = customers.filter(provider=provider)

    total_revenue = invoices.filter(status='paid').aggregate(total=Sum('amount'))['total'] or 0
    this_month_revenue = invoices.filter(
        status='paid', paid_at__year=today.year, paid_at__month=today.month
    ).aggregate(total=Sum('amount'))['total'] or 0

    customer_counts = customers.aggregate(
        active=Count('id', filter=Q(status='active')),
        suspended=Count('id', filter=Q(status='suspended')),
        expired=Count('id', filter=Q(status='expired')),
        total=Count('id'),
    )

    overdue_invoices = invoices.filter(status='pending', due_date__lt=today).count()

    return Response({
        "total_revenue": total_revenue,
        "this_month_revenue": this_month_revenue,
        "customers": customer_counts,
        "overdue_invoices": overdue_invoices,
    })


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


@require_http_methods(["GET", "POST"])
def purchase_page(request, slug):
    """
    Public self-service page: a WiFi customer picks a package and pays
    directly via M-Pesa STK push, no login or admin action needed.
    URL: /pay/<provider-slug>/
    """
    provider = get_object_or_404(Provider, slug=slug, is_active=True)
    packages = Package.objects.filter(provider=provider, is_active=True).order_by('price')

    context = {'provider': provider, 'packages': packages}

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        package_id = request.POST.get('package_id')

        errors = []
        if not full_name:
            errors.append("Please enter your name.")
        if not phone_number:
            errors.append("Please enter your phone number.")
        package = packages.filter(id=package_id).first()
        if not package:
            errors.append("Please select a package.")

        if errors:
            context['errors'] = errors
            context['form_full_name'] = full_name
            context['form_phone_number'] = phone_number
            return render(request, 'billing/purchase.html', context)

        normalized_phone = mpesa.normalize_phone(phone_number)

        customer, _ = Customer.objects.get_or_create(
            provider=provider, phone_number=normalized_phone,
            defaults={'full_name': full_name, 'package': package, 'status': 'active'},
        )
        customer.full_name = full_name
        customer.package = package
        customer.save()

        invoice = Invoice.objects.create(
            customer=customer, package=package, amount=package.price,
            due_date=timezone.now().date(),
        )

        try:
            result = mpesa.stk_push(
                provider=provider,
                phone_number=normalized_phone,
                amount=package.price,
                account_reference=invoice.invoice_number,
                description=f"WiFi-{package.name}",
            )
        except mpesa.MpesaError as e:
            invoice.status = 'cancelled'
            invoice.save()
            logger.error("Self-service STK push failed for %s: %s", provider.business_name, e)
            context['errors'] = [f"Could not start payment. Please try again in a moment."]
            return render(request, 'billing/purchase.html', context)

        payment = Payment.objects.create(
            invoice=invoice,
            phone_number=normalized_phone,
            amount=package.price,
            merchant_request_id=result.get('MerchantRequestID'),
            checkout_request_id=result.get('CheckoutRequestID'),
            status='pending' if result.get('ResponseCode') == '0' else 'failed',
            result_desc=result.get('ResponseDescription', ''),
        )

        return render(request, 'billing/purchase_pending.html', {
            'provider': provider,
            'package': package,
            'phone_number': normalized_phone,
            'payment_id': payment.id,
        })

    return render(request, 'billing/purchase.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def payment_status(request, payment_id):
    """Polled by the purchase-pending page to check whether payment completed."""
    try:
        payment = Payment.objects.get(id=payment_id)
    except Payment.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        "status": payment.status,
        "result_desc": payment.result_desc,
    })
