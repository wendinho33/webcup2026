from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('callsign', 'user', 'sector', 'created_at')
    list_filter = ('sector',)
    search_fields = ('callsign', 'user__username', 'user__email')
    readonly_fields = ('callsign', 'created_at')
