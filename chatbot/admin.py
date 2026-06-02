from django.contrib import admin
from chatbot.models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'category', 'status', 'customer_email', 'created_at', 'short_description')
    list_filter = ('category', 'status')
    search_fields = ('ticket_id', 'description', 'customer_email')
    readonly_fields = ('ticket_id', 'created_at', 'updated_at')
    list_editable = ('status',)
    fields = ('ticket_id', 'category', 'status', 'description', 'customer_email', 'staff_note', 'created_at', 'updated_at')

    def short_description(self, obj):
        return obj.description[:60] + '...' if len(obj.description) > 60 else obj.description
    short_description.short_description = 'Mô tả'
