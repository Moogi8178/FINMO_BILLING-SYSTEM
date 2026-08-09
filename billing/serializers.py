from rest_framework import serializers
from .models import Provider, Package, Customer, Invoice, Payment


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = [
            'id', 'business_name', 'contact_email', 'contact_phone',
            'mpesa_env', 'mpesa_shortcode', 'commission_percentage', 'is_active', 'created_at',
        ]
        # Consumer key/secret/passkey deliberately excluded from API responses -
        # they're write-only via the admin, never read back out.


class PackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Package
        fields = '__all__'
        read_only_fields = ['provider']


class CustomerSerializer(serializers.ModelSerializer):
    package_name = serializers.CharField(source='package.name', read_only=True)

    class Meta:
        model = Customer
        fields = '__all__'
        read_only_fields = ['provider']


class InvoiceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'
        read_only_fields = ['invoice_number']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = [
            'merchant_request_id', 'checkout_request_id', 'mpesa_receipt_number',
            'transaction_date', 'result_code', 'result_desc', 'status',
        ]


class InitiatePaymentSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField()
