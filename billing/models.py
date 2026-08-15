import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Provider(models.Model):
    """
    A WiFi/ISP business using this platform to bill their own customers.
    Each provider has their own M-Pesa Paybill/Till and collects payment
    directly from their customers - money never passes through this
    platform's own account. Providers pay the platform owner a commission
    separately, tracked via CommissionRecord.
    """
    ENV_CHOICES = [
        ('sandbox', 'Sandbox'),
        ('production', 'Production'),
    ]

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='provider'
    )
    business_name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True,
                             help_text="Used in the public purchase page URL, e.g. /pay/<slug>/")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=15, blank=True)

    # Each provider's own M-Pesa Daraja credentials - their customers pay
    # into this shortcode directly, not the platform's.
    mpesa_env = models.CharField(max_length=10, choices=ENV_CHOICES, default='sandbox')
    mpesa_shortcode = models.CharField(max_length=20, blank=True)
    mpesa_consumer_key = models.CharField(max_length=255, blank=True)
    mpesa_consumer_secret = models.CharField(max_length=255, blank=True)
    mpesa_passkey = models.CharField(max_length=255, blank=True)

    commission_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00,
        help_text="Percentage of monthly revenue this provider owes the platform owner"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.business_name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.business_name) or 'provider'
            slug = base_slug
            counter = 1
            while Provider.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def mpesa_base_url(self):
        return (
            'https://sandbox.safaricom.co.ke' if self.mpesa_env == 'sandbox'
            else 'https://api.safaricom.co.ke'
        )


class Package(models.Model):
    """A WiFi subscription package, e.g. '5 Mbps Home - Monthly'."""
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='packages')
    name = models.CharField(max_length=100)
    speed_mbps = models.PositiveIntegerField(help_text="Download speed in Mbps")
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price in KES")
    duration_days = models.PositiveIntegerField(default=30, help_text="Validity period in days")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (KES {self.price}/{self.duration_days}d)"


class Customer(models.Model):
    """A WiFi customer being billed."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired'),
    ]

    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='customers')
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='customer_profile',
        help_text="Linked login account, if this customer has registered for self-service access"
    )
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(
        max_length=15,
        help_text="Format: 2547XXXXXXXX (used for M-Pesa STK push)"
    )
    email = models.EmailField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True)
    package = models.ForeignKey(Package, on_delete=models.SET_NULL, null=True, related_name='customers')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    subscription_start = models.DateField(null=True, blank=True)
    subscription_end = models.DateField(null=True, blank=True)
    router_serial = models.CharField(max_length=100, blank=True, help_text="Optional: equipment/router ID")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('provider', 'phone_number')]

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"

    @property
    def is_expired(self):
        if not self.subscription_end:
            return False
        return self.subscription_end < timezone.now().date()


class Invoice(models.Model):
    """A billing invoice for a customer's package period."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    invoice_number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    package = models.ForeignKey(Package, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"INV-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.full_name} - KES {self.amount}"


class Payment(models.Model):
    """An M-Pesa payment attempt/record linked to an invoice."""
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('pending', 'Pending Confirmation'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled by user'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    phone_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Daraja STK Push identifiers
    merchant_request_id = models.CharField(max_length=100, blank=True, null=True)
    checkout_request_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # Populated once M-Pesa confirms via callback
    mpesa_receipt_number = models.CharField(max_length=50, blank=True, null=True)
    transaction_date = models.CharField(max_length=20, blank=True, null=True)
    result_code = models.CharField(max_length=10, blank=True, null=True)
    result_desc = models.CharField(max_length=255, blank=True, null=True)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='initiated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment {self.id} - {self.phone_number} - {self.status}"


class CommissionRecord(models.Model):
    """
    Tracks what a provider owes the platform owner for a given month,
    based on their revenue collected through this platform. Money is
    NOT moved automatically - this is a record for manual reconciliation
    (the provider pays the platform owner separately, outside the app).
    """
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
    ]

    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='commission_records')
    period_start = models.DateField()
    period_end = models.DateField()
    provider_revenue = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total paid invoices in this period")
    commission_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Amount owed to the platform owner")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unpaid')
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider.business_name} - {self.period_start} to {self.period_end} - KES {self.commission_amount} ({self.status})"


class Lead(models.Model):
    """A prospective customer who hasn't signed up yet."""
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('converted', 'Converted'),
        ('lost', 'Lost'),
    ]
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='leads')
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=15, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.get_status_display()})"


class Ticket(models.Model):
    """A support request from a customer or about a lead."""
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('closed', 'Closed'),
    ]
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='tickets')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    subject = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.subject} ({self.get_status_display()})"


class Device(models.Model):
    """
    Manually-tracked inventory of network equipment (routers, access points,
    fiber links). This is a simple record, not live telemetry - actual
    online/offline status requires integrating with the device's own API
    (e.g. MikroTik RouterOS) or a RADIUS server, which isn't wired in yet.
    """
    CATEGORY_CHOICES = [
        ('router', 'Router'),
        ('access_point', 'Access Point'),
        ('fiber_link', 'Fiber Link'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('maintenance', 'Maintenance'),
        ('retired', 'Retired'),
    ]
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='devices')
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, default='router')
    location = models.CharField(max_length=200, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class Voucher(models.Model):
    """A prepaid access code for a package, redeemable by a customer."""
    STATUS_CHOICES = [
        ('unused', 'Unused'),
        ('used', 'Used'),
    ]
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='vouchers')
    code = models.CharField(max_length=20, unique=True, editable=False)
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name='vouchers')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unused')
    used_by = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='redeemed_vouchers')
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = uuid.uuid4().hex[:10].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.package.name} ({self.get_status_display()})"


class Announcement(models.Model):
    """A message a provider broadcasts to their customers (shown on the customer dashboard)."""
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='announcements')
    message = models.CharField(max_length=300)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.message[:50]
class PlatformBankAccount(models.Model):
    """
    The platform owner's bank account where provider commission payments
    are deposited monthly. Superuser-only - not visible to individual
    WiFi providers. This is a reference record for reconciliation; it
    does not move money automatically.
    """
    bank_name = models.CharField(max_length=150)
    account_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=50)
    branch = models.CharField(max_length=150, blank=True)
    swift_code = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"
