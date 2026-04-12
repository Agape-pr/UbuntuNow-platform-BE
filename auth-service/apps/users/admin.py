from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'username', 'role_badge', 'phone_number', 'is_active', 'date_joined')
    list_filter  = ('role', 'is_active', 'is_staff')
    search_fields = ('email', 'username', 'phone_number')
    ordering = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('UbuntuNow Profile', {'fields': ('role', 'phone_number')}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('UbuntuNow Profile', {'fields': ('email', 'role', 'phone_number')}),
    )

    def role_badge(self, obj):
        colours = {
            'admin':  ('#6366f1', '#eef2ff'),
            'seller': ('#16a34a', '#dcfce7'),
            'buyer':  ('#2563eb', '#dbeafe'),
        }
        fg, bg = colours.get(obj.role, ('#64748b', '#f1f5f9'))
        return format_html(
            '<span style="padding:2px 10px;border-radius:99px;font-size:11px;'
            'font-weight:700;color:{};background:{};">{}</span>',
            fg, bg, obj.role.upper()
        )
    role_badge.short_description = 'Role'
