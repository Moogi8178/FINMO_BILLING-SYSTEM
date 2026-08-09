import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_default_provider(apps, schema_editor):
    """
    Any Package/Customer created before multi-tenancy was added needs to be
    assigned to SOME provider. We create one 'default' provider owned by
    the first superuser (the platform owner's own test account) and attach
    existing rows to it, so nothing existing breaks.
    """
    Provider = apps.get_model('billing', 'Provider')
    Package = apps.get_model('billing', 'Package')
    Customer = apps.get_model('billing', 'Customer')
    User = apps.get_model('auth', 'User')

    orphan_packages = Package.objects.filter(provider__isnull=True)
    orphan_customers = Customer.objects.filter(provider__isnull=True)

    if not orphan_packages.exists() and not orphan_customers.exists():
        return

    owner = User.objects.filter(is_superuser=True).order_by('id').first()
    if owner is None:
        # No superuser exists yet (fresh install) - nothing to backfill against.
        return

    default_provider, _ = Provider.objects.get_or_create(
        owner=owner,
        defaults={'business_name': f"{owner.username}'s WiFi Business"},
    )

    orphan_packages.update(provider=default_provider)
    orphan_customers.update(provider=default_provider)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('billing', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Provider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_name', models.CharField(max_length=150)),
                ('contact_email', models.EmailField(blank=True, max_length=254)),
                ('contact_phone', models.CharField(blank=True, max_length=15)),
                ('mpesa_env', models.CharField(choices=[('sandbox', 'Sandbox'), ('production', 'Production')], default='sandbox', max_length=10)),
                ('mpesa_shortcode', models.CharField(blank=True, max_length=20)),
                ('mpesa_consumer_key', models.CharField(blank=True, max_length=255)),
                ('mpesa_consumer_secret', models.CharField(blank=True, max_length=255)),
                ('mpesa_passkey', models.CharField(blank=True, max_length=255)),
                ('commission_percentage', models.DecimalField(decimal_places=2, default=10.0, max_digits=5, help_text='Percentage of monthly revenue this provider owes the platform owner')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='provider', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='CommissionRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('provider_revenue', models.DecimalField(decimal_places=2, help_text='Total paid invoices in this period', max_digits=12)),
                ('commission_percentage', models.DecimalField(decimal_places=2, max_digits=5)),
                ('commission_amount', models.DecimalField(decimal_places=2, help_text='Amount owed to the platform owner', max_digits=12)),
                ('status', models.CharField(choices=[('unpaid', 'Unpaid'), ('paid', 'Paid')], default='unpaid', max_length=10)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commission_records', to='billing.provider')),
            ],
        ),
        migrations.AddField(
            model_name='package',
            name='provider',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='packages', to='billing.provider'),
        ),
        migrations.AddField(
            model_name='customer',
            name='provider',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='customers', to='billing.provider'),
        ),
        migrations.RunPython(backfill_default_provider, noop_reverse),
        migrations.AlterField(
            model_name='package',
            name='provider',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='packages', to='billing.provider'),
        ),
        migrations.AlterField(
            model_name='customer',
            name='provider',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customers', to='billing.provider'),
        ),
        migrations.AlterField(
            model_name='customer',
            name='phone_number',
            field=models.CharField(help_text='Format: 2547XXXXXXXX (used for M-Pesa STK push)', max_length=15),
        ),
        migrations.AlterUniqueTogether(
            name='customer',
            unique_together={('provider', 'phone_number')},
        ),
    ]
