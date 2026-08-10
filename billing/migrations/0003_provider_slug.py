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
        migrations.AddField(
            model_name='provider',
            name='slug',
            field=models.SlugField(blank=True, default='', max_length=170, help_text='Used in the public purchase page URL, e.g. /pay/<slug>/'),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_slugs, noop_reverse),
        migrations.AlterField(
            model_name='provider',
            name='slug',
            field=models.SlugField(blank=True, max_length=170, unique=True, help_text='Used in the public purchase page URL, e.g. /pay/<slug>/'),
        ),
    ]
