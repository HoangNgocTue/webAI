from django.db import models
from django.contrib.auth.models import User
import uuid


class ChatHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    reply = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.message[:50]}"


class SupportTicket(models.Model):
    CATEGORY_CHOICES = [
        ('order_payment', 'Đặt hàng / Thanh toán'),
        ('account', 'Tài khoản'),
        ('cart_product', 'Giỏ hàng / Sản phẩm'),
        ('delivery_warranty', 'Giao hàng / Bảo hành'),
        ('other', 'Khác'),
    ]
    STATUS_CHOICES = [
        ('open', 'Chờ xử lý'),
        ('in_progress', 'Đang xử lý'),
        ('resolved', 'Đã giải quyết'),
    ]

    ticket_id = models.CharField(max_length=20, unique=True, editable=False)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    customer_email = models.EmailField(blank=True, null=True)
    staff_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            self.ticket_id = "TKT-" + uuid.uuid4().hex[:6].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ticket_id} [{self.get_category_display()}] - {self.status}"

    class Meta:
        ordering = ['-created_at']
