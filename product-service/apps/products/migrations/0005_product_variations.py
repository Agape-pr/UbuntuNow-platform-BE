from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('products', '0004_fix_product_store_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='variations',
            field=models.JSONField(blank=True, default=dict, help_text="e.g. {'colors': ['Red', 'Blue'], 'sizes': ['S', 'M']}", null=True),
        ),
    ]
