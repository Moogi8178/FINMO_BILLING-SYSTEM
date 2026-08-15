from django.contrib import admin
from .models import Provider, Package, Customer, Invoice, Payment, CommissionRecord, Lead, Ticket, Device, Voucher, Announcement, PlatformBankAccount


class ProviderScopedAdmin(admin.ModelAdmin):
    """
    Base admin class: superusers (platform owner) see everything.
    Non-superuser staff (a provider's own login) only see their own data,
    and new records they create are automatically tagged with their provider.
    """
    provider_lookup = 'provider'  # override for models where the path differs

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        provider = getattr(request.user, 'provider', None)
        if provider is None:
            return qs.none()
        return qs.filter(**{self.provider_lookup: provider})

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and not change:
            provider = getattr(request.user, 'provider', None)
            if provider is not None and hasattr(obj, 'provider_id'):
                obj.provider = provider
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Non-superusers shouldn't be able to pick a different provider's
        # packages/customers when filling in a form (e.g. Invoice's customer field)
        if not request.user.is_superuser:
            provider = getattr(request.user, 'provider', None)
            if provider is not None:
                if db_field.name == 'customer':
                    kwargs['queryset'] = Customer.objects.filter(provider=provider)
                elif db_field.name == 'package':
                    kwargs['queryset'] = Package.objects.filter(provider=provider)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    # Providers should NOT see other providers - only the platform owner
    # (superuser) manages this model at all.
    list_display = ('business_name', 'mpesa_shortcode', 'mpesa_env', 'commission_percentage', 'is_active', 'created_at')
    list_filter = ('is_active', 'mpesa_env')
    search_fields = ('business_name', 'contact_email', 'contact_phone')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(owner=request.user)

    def has_add_permission(self, request):
        # Only the platform owner creates new providers (part of onboarding)
        return request.user.is_superuser


@admin.register(Package)
class PackageAdmin(ProviderScopedAdmin):
    list_display = ('name', 'speed_mbps', 'price', 'duration_days', 'is_active', 'provider')
    list_filter = ('is_active',)


@admin.register(Customer)
class CustomerAdmin(ProviderScopedAdmin):
    list_display = ('full_name', 'phone_number', 'package', 'status', 'subscription_end', 'provider')
    list_filter = ('status', 'package')
    search_fields = ('full_name', 'phone_number', 'email')


@admin.register(Invoice)
class InvoiceAdmin(ProviderScopedAdmin):
    provider_lookup = 'customer__provider'
    list_display = ('invoice_number', 'customer', 'amount', 'status', 'due_date', 'paid_at')
    list_filter = ('status',)
    search_fields = ('invoice_number', 'customer__full_name')


@admin.register(Payment)
class PaymentAdmin(ProviderScopedAdmin):
    provider_lookup = 'invoice__customer__provider'
    list_display = ('id', 'invoice', 'phone_number', 'amount', 'status', 'mpesa_receipt_number', 'created_at')
    list_filter = ('status',)
    readonly_fields = (
        'merchant_request_id', 'checkout_request_id', 'mpesa_receipt_number',
        'transaction_date', 'result_code', 'result_desc',
    )


@admin.register(CommissionRecord)
class CommissionRecordAdmin(admin.ModelAdmin):
    # Commission records are platform-owner-only (a provider shouldn't see
    # or edit what they owe you)
    list_display = ('provider', 'period_start', 'period_end', 'provider_revenue', 'commission_percentage', 'commission_amount', 'status')
    list_filter = ('status',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.none()

    def has_module_permission(self, request):
        return request.user.is_superuser
@admin.register(Lead)
class LeadAdmin(ProviderScopedAdmin):
    list_display = ('full_name', 'phone_number', 'status', 'provider', 'created_at')
    list_filter = ('status',)


@admin.register(Ticket)
class TicketAdmin(ProviderScopedAdmin):
    list_display = ('subject', 'customer', 'status', 'provider', 'created_at')
    list_filter = ('status',)


@admin.register(Device)
class DeviceAdmin(ProviderScopedAdmin):
    list_display = ('name', 'category', 'status', 'location', 'provider')
    list_filter = ('category', 'status')


@admin.register(Voucher)
class VoucherAdmin(ProviderScopedAdmin):
    list_display = ('code', 'package', 'status', 'used_by', 'provider')
    list_filter = ('status',)


@admin.register(Announcement)
class AnnouncementAdmin(ProviderScopedAdmin):
    list_display = ('message', 'is_active', 'provider', 'created_at')
    list_filter = ('is_active',)
