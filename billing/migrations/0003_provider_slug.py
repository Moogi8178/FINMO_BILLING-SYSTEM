from django.db import migrations, models
from django.utils.text import slugify


def backfill_slugs(apps, schema_editor):
    Provider = apps.get_model('billing', 'Provider')
    for provider in Provider.objects.filter(slug=''):
        base_slug = slugify(provider.business_name) or 'provider'
        slug = base_slug
        counter = 1
        while Provider.objects.filter(slug=slug).exclude(pk=provider.pk).exists():
            counter += 1
            slug = f"{base_slug}-{counter}"
        provider.slug = slug
        provider.save(update_fields=['slug'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_multi_tenant_providers'),
    ]

    operations = [
        # Uses raw idempotent SQL for the actual database changes (safe to
        # re-run even if a previous deploy partially applied this migration),
        # while keeping Django's model state in sync via state_operations.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='provider',
                    name='slug',
                    field=models.SlugField(blank=True, max_length=170, unique=True, help_text='Used in the public purchase page URL, e.g. /pay/<slug>/'),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE billing_provider ADD COLUMN IF NOT EXISTS slug varchar(170) DEFAULT '' NOT NULL;",
                    reverse_sql="ALTER TABLE billing_provider DROP COLUMN IF EXISTS slug;",
                ),
                migrations.RunSQL(
                    sql="CREATE UNIQUE INDEX IF NOT EXISTS billing_provider_slug_key ON billing_provider (slug);",
                    reverse_sql="DROP INDEX IF EXISTS billing_provider_slug_key;",
                ),
                migrations.RunSQL(
                    sql="CREATE INDEX IF NOT EXISTS billing_provider_slug_f7fbd7b1_like ON billing_provider (slug varchar_pattern_ops);",
                    reverse_sql="DROP INDEX IF EXISTS billing_provider_slug_f7fbd7b1_like;",
                ),
            ],
        ),
        migrations.RunPython(backfill_slugs, noop_reverse),
    ]
