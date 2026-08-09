from rest_framework import serializers
from .models import Package, Customer, Invoice, Payment


class PackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Package
        fields = '__all__'


class CustomerSerializer(serializers.ModelSerializer):
    package_name = serializers.CharField(source='package.name', read_only=True)

    class Meta:
        model = Customer
        fields = '__all__'


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
