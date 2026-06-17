from django.contrib import admin
from .models import *
from django.utils.timezone import localtime, now

# Tùy chỉnh hiển thị Order trong admin
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'get_local_date_order', 'get_local_approved_date', 'complete', 'transaction_id', 'status')
    list_filter = ('complete', 'status', 'date_order')
    search_fields = ('customer__username', 'transaction_id')
    actions = ['approve_orders', 'reject_orders']  # Thêm các hành động

    # Phương thức để hiển thị thời gian đặt hàng
    def get_local_date_order(self, obj):
        return localtime(obj.date_order).strftime('%d-%m-%Y %H:%M:%S')
    get_local_date_order.short_description = 'Thời gian đặt hàng'

    # Hiển thị thời gian duyệt đơn hàng
    def get_local_approved_date(self, obj):
        if obj.approved_date:
            return localtime(obj.approved_date).strftime('%d-%m-%Y %H:%M:%S')
        return "Chưa duyệt"
    get_local_approved_date.short_description = 'Thời gian duyệt'

    # Hành động duyệt đơn
    @admin.action(description='Duyệt các đơn hàng đã chọn')
    def approve_orders(self, request, queryset):
        updated = queryset.update(status='approved', approved_date=now())  # Đặt trạng thái "approved"
        self.message_user(request, f'{updated} đơn hàng đã được duyệt.')

    # Hành động từ chối đơn
    @admin.action(description='Từ chối các đơn hàng đã chọn')
    def reject_orders(self, request, queryset):
        updated = queryset.update(status='canceled', approved_date=None)  # Đặt trạng thái "canceled"
        self.message_user(request, f'{updated} đơn hàng đã bị từ chối.')

# Tùy chỉnh hiển thị OrderItem trong admin
@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'order', 'quantity', 'get_local_date_added')

    # Phương thức tùy chỉnh để hiển thị thời gian thêm vào đơn hàng
    def get_local_date_added(self, obj):
        return localtime(obj.date_added).strftime('%d-%m-%Y %H:%M:%S')
    get_local_date_added.short_description = 'Thời gian thêm vào'

# Các model khác vẫn giữ nguyên
admin.site.register(Product)
admin.site.register(Category)
admin.site.register(ShippingAddress)