from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

# Category model
class Category(models.Model):
    sub_category = models.ForeignKey('self', on_delete=models.CASCADE, related_name='sub_categories', null=True, blank=True)
    is_sub = models.BooleanField(default=False)
    name = models.CharField(max_length=200, null=True)
    slug = models.SlugField(max_length=200, unique=True)

    def __str__(self):
        return self.name


# User registration form
class CreateUserForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']


# -------- Màu sắc cơ bản --------
COLOR_CHOICES = [
    ('red', 'Đỏ'),
    ('blue', 'Xanh dương'),
    ('green', 'Xanh lá'),
    ('yellow', 'Vàng'),
    ('black', 'Đen'),
    ('white', 'Trắng'),
    ('gray', 'Xám'),
    ('silver', 'Bạc'),
    ('gold', 'Vàng kim'),
    ('space_gray', 'Xám không gian'),
]


# -------- Model sản phẩm --------
class Product(models.Model):
    category = models.ManyToManyField(Category, related_name='products')
    name = models.CharField(max_length=200, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)  # Tăng max_digits lên 12 phòng trường hợp giá đồ công nghệ lên đến hàng trăm triệu
    digital = models.BooleanField(default=False, null=True, blank=False)
    image = models.ImageField(null=True, blank=True)
    detail = models.TextField(null=True, blank=True)
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, null=True, blank=True, default='black')
    
    # Các trường cấu hình công nghệ mới
    cpu = models.CharField(max_length=100, null=True, blank=True)
    gpu = models.CharField(max_length=100, null=True, blank=True)
    ram = models.CharField(max_length=50, null=True, blank=True)
    storage = models.CharField(max_length=50, null=True, blank=True)
    stock = models.IntegerField(default=10)

    def __str__(self):
        return f"{self.name} ({self.get_color_display()})" if self.color else self.name

    @property
    def ImageURL(self):
        try:
            url = self.image.url
        except:
            url = ''
        return url


# Order model
class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Chưa duyệt'),
        ('approved', 'Đã duyệt'),
        ('canceled', 'Đã hủy'),
    ]

    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date_order = models.DateTimeField(auto_now_add=True)
    complete = models.BooleanField(default=False, null=True, blank=False)
    transaction_id = models.CharField(max_length=200, null=True)
    approved_date = models.DateTimeField(null=True, blank=True)  # Lưu thời gian duyệt đơn
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')  # Trạng thái đơn hàng

    def __str__(self):
        return f"Order #{self.id}"

    @property
    def get_cart_items(self):
        """Tổng số lượng sản phẩm trong giỏ hàng."""
        return sum(item.quantity for item in self.orderitem_set.all())

    @property
    def get_cart_total(self):
        """Tổng giá trị đơn hàng."""
        total = sum(item.product.price * item.quantity for item in self.orderitem_set.all() if item.product and item.product.price)
        return total

    @property
    def customer_name(self):
        """Tên khách hàng (ưu tiên họ tên, sau đó là username)."""
        if self.customer:
            full_name = f"{self.customer.first_name} {self.customer.last_name}".strip()
            return full_name if full_name else self.customer.username
        return "Không có tên khách hàng"

    @property
    def customer_email(self):
        """Email khách hàng."""
        return self.customer.email if self.customer else "Không có email khách hàng"

    @property
    def is_approved(self):
        """Kiểm tra đơn hàng đã được duyệt hay chưa."""
        return self.status == 'approved'

    @property
    def has_invoice(self):
        """Kiểm tra nếu đơn hàng có hóa đơn hay chưa."""
        # Giả sử bạn có một mối quan hệ với model `Invoice` hoặc một trường nào đó cho biết đơn hàng có hóa đơn hay không
        return self.status == 'approved' and self.transaction_id is not None


# OrderItem model
class OrderItem(models.Model):
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, blank=True, null=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, blank=True, null=True)
    quantity = models.IntegerField(default=0, null=True, blank=True)
    date_added = models.DateTimeField(auto_now_add=True)

    @property
    def get_total(self):
        return self.product.price * self.quantity


# ShippingAddress model
class ShippingAddress(models.Model):
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, blank=True, null=True)
    address = models.CharField(max_length=200, null=True)
    city = models.CharField(max_length=200, null=True)
    state = models.CharField(max_length=200, null=True)
    mobile = models.CharField(max_length=10, null=True)
    date_added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.address
    
from django.db import models
from django.utils.timezone import now
from django.contrib.auth.models import User
class Invoice(models.Model):
    order = models.OneToOneField('Order', on_delete=models.CASCADE)  # Liên kết với Order
    invoice_date = models.DateTimeField(default=now)
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Hóa đơn #{self.id} - {self.order.customer.username if self.order.customer else 'Guest'}"

    def formatted_invoice_date(self):
        # Chuyển đổi thời gian thành định dạng 24 giờ
        return self.invoice_date.strftime('%d/%m/%Y %H:%M')
