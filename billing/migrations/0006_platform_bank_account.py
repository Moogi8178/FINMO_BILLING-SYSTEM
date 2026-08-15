from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0005_leads_tickets_devices_vouchers_announcements'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlatformBankAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bank_name', models.CharField(max_length=150)),
                ('account_name', models.CharField(max_length=150)),
                ('account_number', models.CharField(max_length=50)),
                ('branch', models.CharField(blank=True, max_length=150)),
                ('swift_code', models.CharField(blank=True, max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
