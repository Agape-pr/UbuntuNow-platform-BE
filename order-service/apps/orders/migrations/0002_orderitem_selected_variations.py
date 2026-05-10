from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='selected_variations',
            field=models.JSONField(blank=True, default=dict, help_text="User selected options e.g. {'color': 'Red', 'size': 'M'}", null=True),
        ),
    ]
