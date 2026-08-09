import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Package',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('speed_mbps', models.PositiveIntegerField(help_text='Download speed in Mbps')),
                ('price', models.DecimalField(decimal_places=2, help_text='Price in KES', max_digits=10)),
                ('duration_days', models.PositiveIntegerField(default=30, help_text='Validity period in days')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=150)),
                ('phone_number', models.CharField(help_text='Format: 2547XXXXXXXX (used for M-Pesa STK push)', max_length=15, unique=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('address', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(choices=[('active', 'Active'), ('suspended', 'Suspended'), ('expired', 'Expired')], default='active', max_length=10)),
                ('subscription_start', models.DateField(blank=True, null=True)),
                ('subscription_end', models.DateField(blank=True, null=True)),
                ('router_serial', models.CharField(blank=True, help_text='Optional: equipment/router ID', max_length=100)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('package', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='customers', to='billing.package')),
            ],
        ),
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice_number', models.CharField(editable=False, max_length=20, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid'), ('overdue', 'Overdue'), ('cancelled', 'Cancelled')], default='pending', max_length=10)),
                ('due_date', models.DateField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='billing.customer')),
                ('package', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='billing.package')),
            ],
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone_number', models.CharField(max_length=15)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('merchant_request_id', models.CharField(blank=True, max_length=100, null=True)),
                ('checkout_request_id', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('mpesa_receipt_number', models.CharField(blank=True, max_length=50, null=True)),
                ('transaction_date', models.CharField(blank=True, max_length=20, null=True)),
                ('result_code', models.CharField(blank=True, max_length=10, null=True)),
                ('result_desc', models.CharField(blank=True, max_length=255, null=True)),
                ('status', models.CharField(choices=[('initiated', 'Initiated'), ('pending', 'Pending Confirmation'), ('completed', 'Completed'), ('failed', 'Failed'), ('cancelled', 'Cancelled by user')], default='initiated', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='billing.invoice')),
            ],
        ),
    ]
