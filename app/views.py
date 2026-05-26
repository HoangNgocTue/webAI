from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import *
import json
import unicodedata
from django.db.models import Q
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages


def normalize_search_text(value):
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.lower().strip()


def expand_search_terms(keyword):
    normalized = normalize_search_text(keyword)
    terms = {keyword.strip(), normalized}

    synonyms = {
        "may tinh": ["laptop", "notebook", "macbook", "máy tính xách tay"],
        "laptop": ["may tinh", "máy tính", "notebook", "macbook"],
        "dien thoai": ["phone", "iphone", "samsung", "xiaomi", "điện thoại"],
        "linh kien": ["cpu", "gpu", "ram", "card", "pc", "linh kiện"],
        "card do hoa": ["gpu", "vga", "rtx", "nvidia", "radeon", "card đồ họa"],
        "o cung": ["storage", "ssd", "hdd", "512gb", "1tb", "ổ cứng"],
        "chuot": ["mouse", "logitech", "chuột"],
        "ban phim": ["keyboard", "keychron", "bàn phím"],
        "tai nghe": ["headphone", "sony", "tai nghe"],
        "ram": ["8gb", "16gb", "32gb", "memory"],
    }

    for key, values in synonyms.items():
        if key in normalized:
            terms.update(values)

    for word in normalized.split():
        if len(word) >= 2:
            terms.add(word)

    return [term for term in terms if term]


def product_matches_terms(product, terms):
    haystack = " ".join(
        str(value or "")
        for value in [
            product.name,
            product.detail,
            product.cpu,
            product.gpu,
            product.ram,
            product.storage,
            product.color,
            " ".join(category.name or "" for category in product.category.all()),
            " ".join(category.slug or "" for category in product.category.all()),
        ]
    )
    normalized_haystack = normalize_search_text(haystack)
    normalized_terms = [normalize_search_text(term) for term in terms]
    return any(term and term in normalized_haystack for term in normalized_terms)

def detail(request):
    if request.user.is_authenticated:
        customer = request.user
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        items = order.orderitem_set.all()
        cartItems = order.get_cart_items
        user_not_login = "hidden"
        user_login = "show"
    else:
        items = []
        order = {'get_cart_total': 0, 'get_cart_items': 0}
        cartItems = 0
        user_not_login = "show"
        user_login = "hidden"
    id = request.GET.get('id','')    
    products = Product.objects.filter(id=id)
    categories = Category.objects.filter(is_sub =False)
    context = {
        'products': products,
        'categories': categories,
        'items': items,
        'order': order,
        'cartItems': cartItems,
        'user_not_login': user_not_login,
        'user_login': user_login
    }
    return render(request, 'app/detail.html', context)

# Tìm kiếm sản phẩm
def category(request):
    categories = Category.objects.filter(is_sub=False)
    active_category = request.GET.get('category', '')  # Lấy slug danh mục từ URL

    # Kiểm tra nếu active_category có giá trị
    if active_category:
        # Lọc sản phẩm dựa vào slug của Category
        categories_with_slug = Category.objects.filter(slug=active_category)
        products = Product.objects.filter(category__in=categories_with_slug)  # Lọc sản phẩm thuộc về những Category có slug này
    else:
        products = Product.objects.all()  # Nếu không có slug thì hiển thị tất cả sản phẩm

    if request.user.is_authenticated:
        customer = request.user
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        items = order.orderitem_set.all()
        cartItems = order.get_cart_items
        user_not_login = "hidden"
        user_login = "show"
    else:
        items = []
        order = {'get_cart_total': 0, 'get_cart_items': 0}
        cartItems = 0
        user_not_login = "show"
        user_login = "hidden"
        customer = None  # Ensure 'customer' is defined when the user is not logged in
        order, created = Order.objects.get_or_create(customer=customer, complete=False)

    context = {
        'items': items,
        'order': order,
        'cartItems': cartItems,
        'user_not_login': user_not_login,
        'user_login': user_login,
        'categories': categories,
        'products': products,
        'active_category': active_category
    }
    return render(request, 'app/category.html', context)
def search(request):
    searched = ''  # Đảm bảo rằng searched luôn được định nghĩa
    keys = []  # Danh sách sản phẩm mặc định là rỗng

    if request.method in ["POST", "GET"]:
        searched = (request.POST.get("searched") or request.GET.get("searched") or "").strip()

        if searched:
            terms = expand_search_terms(searched)
            query = Q()
            for term in terms:
                query |= (
                    Q(name__icontains=term)
                    | Q(detail__icontains=term)
                    | Q(cpu__icontains=term)
                    | Q(gpu__icontains=term)
                    | Q(ram__icontains=term)
                    | Q(storage__icontains=term)
                    | Q(color__icontains=term)
                    | Q(category__name__icontains=term)
                    | Q(category__slug__icontains=term)
                )

            orm_matches = Product.objects.filter(query).prefetch_related("category").distinct()
            normalized_matches = [
                product
                for product in Product.objects.prefetch_related("category").all()
                if product_matches_terms(product, terms)
            ]
            merged = {product.id: product for product in orm_matches}
            merged.update({product.id: product for product in normalized_matches})
            keys = sorted(merged.values(), key=lambda product: product.price)

    # Kiểm tra xem người dùng đã đăng nhập chưa
    if request.user.is_authenticated:
        customer = request.user
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        items = order.orderitem_set.all()
        cartItems = order.get_cart_items  # Lấy tổng số lượng sản phẩm trong giỏ hàng
        user_not_login = "hidden"
        user_login = "show"
    else:
        items = []
        order = {'get_cart_total': 0, 'get_cart_items': 0}  # Giả lập dữ liệu nếu người dùng không đăng nhập
        cartItems = 0  # Tổng số sản phẩm mặc định là 0
        user_not_login = "show"
        user_login = "hidden"
        # Không cần tạo 'order' nếu người dùng chưa đăng nhập
    categories = Category.objects.filter(is_sub=False)
    products = Product.objects.all()  # Lấy danh sách sản phẩm để hiển thị
    return render(request, 'app/search.html', {
        "searched": searched,
        "keys": keys,
        'categories': categories,
        'products': products,
        'cartItems': cartItems,
        'user_not_login': user_not_login,
        'user_login': user_login
    })

# Hàm đăng ký người dùng mới
def register(request):
    form = CreateUserForm()
    if request.method == "POST":
        form = CreateUserForm(request.POST)
        user_not_login = "hidden"
        user_login = "show"
        if form.is_valid():
            form.save()
            return redirect('login')
    user_not_login = "show"
    user_login = "hidden"
    if request.user.is_authenticated:
        customer = request.user
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        items = order.orderitem_set.all()
        cartItems = order.get_cart_items
        user_not_login = "hidden"
        user_login = "show"
    else:
        items = []
        order = {'get_cart_total': 0, 'get_cart_items': 0}
        cartItems = 0
    context = {'form': form,
               'user_not_login': user_not_login,

        'user_login': user_login,
        'items': items,
        'order': order,
        'cartItems': cartItems,
               }
    return render(request, 'app/register.html', context)


# Hàm đăng nhập
def loginPage(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        user_not_login = "hidden"
        user_login = "show"
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.info(request, 'user or password not correct!')
    if request.user.is_authenticated:
        customer = request.user
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        items = order.orderitem_set.all()
        cartItems = order.get_cart_items
        user_not_login = "hidden"
        user_login = "show"
    else:
        items = []
        order = {'get_cart_total': 0, 'get_cart_items': 0}
        cartItems = 0
    user_not_login = "show"
    user_login = "hidden"
    context = { 'items': items,
        'order': order,
        'cartItems': cartItems,
        'user_not_login': user_not_login,

        'user_login': user_login
        }
    return render(request, 'app/login.html', context)


# Hàm đăng xuất
def logoutPage(request):
    logout(request)
    return redirect('login')


# Trang chủ
def home(request):
    if request.user.is_authenticated:
        customer = request.user
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        items = order.orderitem_set.all()
        cartItems = order.get_cart_items  # Lấy tổng số lượng sản phẩm trong giỏ hàng
        user_not_login = "hidden"
        user_login = "show"
    else:
        items = []
        order = {'get_cart_total': 0, 'get_cart_items': 0}  # Giả lập dữ liệu nếu người dùng không đăng nhập
        cartItems = 0  # Tổng số sản phẩm mặc định là 0
        user_not_login = "show"
        user_login = "hidden"
    categories = Category.objects.filter(is_sub =False)
    active_category = request.GET.get('category','')

    products = Product.objects.all()  # Lấy danh sách sản phẩm để hiển thị
    context = {
        'categories': categories,
        'active_category': active_category,
        'products': products,
        'cartItems': cartItems,
        'user_not_login': user_not_login,
        'user_login': user_login
    }
    return render(request, 'app/home.html', context)


# Giỏ hàng
def cart(request):
    if request.user.is_authenticated:
        customer = request.user
        order, created = Order.objects.get_or_create(customer=customer, complete=False)
        items = order.orderitem_set.all()
        cartItems = order.get_cart_items
        user_not_login = "hidden"
        user_login = "show"
    else:
        items = []
        order = {'get_cart_total': 0, 'get_cart_items': 0}
        cartItems = 0
        user_not_login = "show"
        user_login = "hidden"
    categories = Category.objects.filter(is_sub =False)
    context = {
        'categories': categories,
        'items': items,
        'order': order,
        'cartItems': cartItems,
        'user_not_login': user_not_login,
        'user_login': user_login
    }
    return render(request, 'app/cart.html', context)

# Cập nhật giỏ hàng
def updateItem(request):
    data = json.loads(request.body)
    productId = data['productId']
    action = data['action']

    customer = request.user
    product = Product.objects.get(id=productId)
    order, created = Order.objects.get_or_create(customer=customer, complete=False)
    orderItem, created = OrderItem.objects.get_or_create(order=order, product=product)

    if action == 'add':
        orderItem.quantity += 1
    elif action == 'remove':
        orderItem.quantity -= 1

    if orderItem.quantity <= 0:
        orderItem.delete()
    else:
        orderItem.save()  # Lưu thay đổi nếu không bị xóa

    # Tính lại tổng số lượng và tổng giá trị
    cart_total = order.get_cart_total
    cart_items = order.get_cart_items

    return JsonResponse({
        'quantity': orderItem.quantity if orderItem.id else 0,
        'cart_total': cart_total,
        'cart_items': cart_items
    })
#

from django.shortcuts import render, redirect
from django.utils.timezone import now, localtime
from django.contrib import messages
from .models import Order, OrderItem, Category, Invoice, ShippingAddress  # Đảm bảo Invoice đã được thêm

def checkout(request):
    # Kiểm tra nếu người dùng đã đăng nhập
    user = request.user if request.user.is_authenticated else None
    if not user:
        messages.warning(request, "Bạn cần đăng nhập để thanh toán!")
        return redirect('login')

    user_not_login = "hidden" if user else "show"
    user_login = "show" if user else "hidden"

    # Kiểm tra giỏ hàng
    cartItems = 0
    order = None
    items = []

    try:
        order = Order.objects.get(customer=user, complete=False)
        items = order.orderitem_set.select_related('product').all()
        cartItems = order.get_cart_items
    except Order.DoesNotExist:
        messages.error(request, "Giỏ hàng của bạn trống!")
        return redirect('cart')  # Nếu không có đơn hàng, chuyển về giỏ hàng

    if cartItems <= 0:
        messages.error(request, "Giỏ hàng của bạn trống!")
        return redirect('cart')

    # Xử lý POST request khi người dùng bấm "Đặt hàng"
    if request.method == 'POST':
        if order:
            full_name = (request.POST.get("name") or "").strip()
            address = (request.POST.get("address") or "").strip()
            city = (request.POST.get("city") or "").strip()
            state = (request.POST.get("state") or "").strip()
            mobile = (request.POST.get("mobile") or request.POST.get("zipcode") or "").strip()

            if not address or not city or not mobile:
                messages.error(request, "Vui lòng nhập đầy đủ địa chỉ, thành phố và số điện thoại.")
                return redirect('checkout')

            if full_name:
                name_parts = full_name.split(maxsplit=1)
                user.first_name = name_parts[0]
                user.last_name = name_parts[1] if len(name_parts) > 1 else ""
                user.save(update_fields=["first_name", "last_name"])

            current_time = localtime(now())
            order.date_order = current_time
            order.complete = True
            order.status = 'pending'
            order.transaction_id = f"ORDER-{order.id}-{int(current_time.timestamp())}"
            order.save()

            ShippingAddress.objects.update_or_create(
                order=order,
                defaults={
                    "customer": user,
                    "address": address,
                    "city": city,
                    "state": state,
                    "mobile": mobile,
                },
            )

            for item in items:
                if item.product:
                    item.product.stock = max(item.product.stock - item.quantity, 0)
                    item.product.save(update_fields=["stock"])

            # Tạo hóa đơn cho đơn hàng
            invoice, created = Invoice.objects.update_or_create(
                order=order,
                defaults={
                    "invoice_date": current_time,
                    "customer": user,
                    "total_amount": order.get_cart_total,
                },
            )
            messages.success(
                request,
                f"Đặt hàng thành công! Hóa đơn #{invoice.id} đã được tạo lúc {current_time.strftime('%H:%M:%S, %d-%m-%Y')}"
            )
            return redirect('invoice_detail', id=invoice.id)  # Chuyển hướng đến trang hóa đơn chi tiết
        else:
            messages.error(request, "Không có giỏ hàng để đặt!")
            return redirect('cart')

    # Lấy danh mục sản phẩm để hiển thị
    categories = Category.objects.filter(is_sub=False)

    # Truyền thông tin vào context
    context = {
        'categories': categories,
        'items': items,
        'order': order,
        'cartItems': cartItems,
        'user_not_login': user_not_login,
        'user_login': user_login,
    }

    return render(request, 'app/checkout.html', context)


from django.shortcuts import render, get_object_or_404
from .models import Invoice

def invoice_detail(request, id):
    # Sử dụng get_object_or_404 để đảm bảo nếu không tìm thấy hóa đơn sẽ trả về 404
    invoice = get_object_or_404(Invoice, id=id)

    categories = Category.objects.filter(is_sub=False)
    if request.user.is_authenticated:
        order, created = Order.objects.get_or_create(customer=request.user, complete=False)
        cartItems = order.get_cart_items
        user_not_login = "hidden"
        user_login = "show"
    else:
        cartItems = 0
        user_not_login = "show"
        user_login = "hidden"

    return render(request, 'app/invoice_detail.html', {
        'invoice': invoice,
        'categories': categories,
        'cartItems': cartItems,
        'user_not_login': user_not_login,
        'user_login': user_login,
    })




def order_history(request):
    if request.user.is_authenticated:
        user = request.user
        if user.is_staff or user.is_superuser:
            orders = Order.objects.filter(complete=True).select_related('customer').prefetch_related('orderitem_set__product').order_by('-date_order')
            is_staff_history = True
        else:
            orders = Order.objects.filter(customer=user, complete=True).select_related('customer').prefetch_related('orderitem_set__product').order_by('-date_order')
            is_staff_history = False
        categories = Category.objects.filter(is_sub=False)
        user_not_login = "hidden"
        user_login = "show"
    else:
        messages.warning(request, "Bạn cần đăng nhập để xem lịch sử đơn hàng!")
        return redirect('login')

    total_spent = 0
    total_items = 0
    approved_orders = 0
    pending_orders = 0
    canceled_orders = 0

    # Truyền hóa đơn tương ứng cho từng đơn hàng
    for order in orders:
        total_spent += order.get_cart_total
        total_items += order.get_cart_items
        if order.status == 'approved':
            approved_orders += 1
        elif order.status == 'canceled':
            canceled_orders += 1
        else:
            pending_orders += 1
        try:
            order.invoice_obj = order.invoice  # Gắn invoice vào từng order
        except Invoice.DoesNotExist:
            order.invoice_obj = None  # Nếu chưa có hóa đơn thì gán None

    context = {
        'orders': orders,
        'categories': categories,
        'user_not_login': user_not_login,
        'user_login': user_login,
        'total_orders': orders.count(),
        'total_spent': total_spent,
        'total_items': total_items,
        'approved_orders': approved_orders,
        'pending_orders': pending_orders,
        'canceled_orders': canceled_orders,
        'is_staff_history': is_staff_history,
    }
    return render(request, 'app/order_history.html', context)


# ===================================================================
# 📊 ADMIN DASHBOARD - THỐNG KÊ DOANH THU & ĐƠN HÀNG
# ===================================================================
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum, Count, Q
from datetime import datetime, timedelta

def is_staff(user):
    return user.is_staff or user.is_superuser

@user_passes_test(is_staff)
def admin_dashboard(request):
    """
    Dashboard quản trị chuyên nghiệp: doanh thu, đơn hàng, sản phẩm bán chạy, khách hàng.
    """
    # Tính toán doanh thu
    total_revenue = Invoice.objects.aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Tính doanh thu theo từng tháng trong 12 tháng gần đây
    today = datetime.now()
    months_data = []
    for i in range(11, -1, -1):
        month_date = today - timedelta(days=i*30)
        month_str = month_date.strftime('%Y-%m')
        revenue_month = Invoice.objects.filter(
            invoice_date__year=month_date.year,
            invoice_date__month=month_date.month
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        months_data.append({'month': month_str, 'revenue': float(revenue_month)})
    
    # Thống kê đơn hàng theo status
    orders_pending = Order.objects.filter(status='pending').count()
    orders_approved = Order.objects.filter(status='approved').count()
    orders_canceled = Order.objects.filter(status='canceled').count()
    total_orders = Order.objects.count()
    
    # Top 5 sản phẩm bán chạy
    top_products = OrderItem.objects.values('product__name', 'product__id').annotate(
        total_qty=Sum('quantity'),
        total_revenue=Sum('quantity') * Sum('product__price')
    ).order_by('-total_qty')[:5]
    
    # Thống kê khách hàng
    total_customers = User.objects.filter(is_staff=False).count()
    active_customers = Order.objects.filter(complete=True).values('customer').distinct().count()
    
    # Tổng số sản phẩm trong kho
    total_products = Product.objects.count()
    total_stock = Product.objects.aggregate(total=Sum('stock'))['total'] or 0
    
    context = {
        'total_revenue': f"{total_revenue:,.0f}".replace(",", "."),
        'total_orders': total_orders,
        'orders_pending': orders_pending,
        'orders_approved': orders_approved,
        'orders_canceled': orders_canceled,
        'total_customers': total_customers,
        'active_customers': active_customers,
        'total_products': total_products,
        'total_stock': total_stock,
        'months_data': json.dumps(months_data),  # Để dùng với Chart.js
        'top_products': top_products[:5],
    }
    
    return render(request, 'app/admin_dashboard.html', context)
