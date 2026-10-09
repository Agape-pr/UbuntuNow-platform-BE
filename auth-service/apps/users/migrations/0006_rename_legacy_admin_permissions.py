from django.db import migrations

# Early admin accounts were created with permission ids that were later renamed.
LEGACY_TO_CURRENT = {
    'manage_buyers': 'manage_users',
    'manage_products': 'view_orders',
}


def rename_permissions(apps, schema_editor):
    User = apps.get_model('users', 'User')
    for user in User.objects.filter(role='admin'):
        perms = user.admin_permissions or []
        updated = []
        for perm in perms:
            perm = LEGACY_TO_CURRENT.get(perm, perm)
            if perm not in updated:
                updated.append(perm)
        if updated != perms:
            user.admin_permissions = updated
            user.save(update_fields=['admin_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_audit_and_admin_login'),
    ]

    operations = [
        migrations.RunPython(rename_permissions, migrations.RunPython.noop),
    ]
