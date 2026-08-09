import uuid
from django.db import models
from django.utils import timezone


class Package(models.Model):
    """A WiFi subscription package, e.g. '5 Mbps Home - Monthly'."""
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

    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(
        max_length=15,
        unique=True,
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
