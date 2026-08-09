"""
Run this daily (e.g. via cron) to auto-generate invoices for customers
whose subscription is expiring within the next N days and who don't
already have a pending invoice.

Usage: python manage.py generate_invoices
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from billing.models import Customer, Invoice


class Command(BaseCommand):
    help = 'Generate pending invoices for customers due for renewal'

    def add_arguments(self, parser):
        parser.add_argument('--days-ahead', type=int, default=3,
                             help='Generate invoices this many days before expiry')

    def handle(self, *args, **options):
        days_ahead = options['days_ahead']
        cutoff = timezone.now().date() + timedelta(days=days_ahead)

        customers = Customer.objects.filter(
            status__in=['active', 'expired'],
            package__isnull=False,
            subscription_end__lte=cutoff,
        )

        created = 0
        for customer in customers:
            already_pending = Invoice.objects.filter(customer=customer, status='pending').exists()
            if already_pending:
                continue

            Invoice.objects.create(
                customer=customer,
                package=customer.package,
                amount=customer.package.price,
                due_date=customer.subscription_end or timezone.now().date(),
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f'Created {created} invoice(s).'))
