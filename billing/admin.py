from django.contrib import admin
from .models import Package, Customer, Invoice, Payment


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'speed_mbps', 'price', 'duration_days', 'is_active')
    list_filter = ('is_active',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone_number', 'package', 'status', 'subscription_end')
    list_filter = ('status', 'package')
    search_fields = ('full_name', 'phone_number', 'email')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'amount', 'status', 'due_date', 'paid_at')
    list_filter = ('status',)
    search_fields = ('invoice_number', 'customer__full_name')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'phone_number', 'amount', 'status', 'mpesa_receipt_number', 'created_at')
    list_filter = ('status',)
    readonly_fields = (
        'merchant_request_id', 'checkout_request_id', 'mpesa_receipt_number',
        'transaction_date', 'result_code', 'result_desc',
    )
