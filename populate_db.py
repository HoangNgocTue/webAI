import os
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webbanhang.settings")

import django

django.setup()

from django.contrib.auth.models import User
from django.utils import timezone

from app.models import Category, Invoice, Order, OrderItem, Product, ShippingAddress
from chatbot.models import ChatHistory


TECH_PRODUCTS = [
    {
        "category": "laptop",
        "name": "ASUS ROG Strix G16 RTX 4060",
        "price": 32990000,
        "color": "black",
        "cpu": "Intel Core i7-13650HX",
        "gpu": "NVIDIA RTX 4060 8GB",
        "ram": "16GB",
        "storage": "512GB SSD",
        "stock": 8,
        "image": "download_1.webp",
        "detail": "Laptop gaming mạnh mẽ cho game thủ, thiết kế tản nhiệt tốt và màn hình tần số quét cao.",
    },
    {
        "category": "laptop",
        "name": "Dell XPS 13 Plus",
        "price": 28990000,
        "color": "silver",
        "cpu": "Intel Core i7-1360P",
        "gpu": "Intel Iris Xe",
        "ram": "16GB",
        "storage": "512GB SSD",
        "stock": 6,
        "image": "download_2.webp",
        "detail": "Ultrabook cao cấp, mỏng nhẹ, phù hợp làm việc văn phòng và sáng tạo nội dung.",
    },
    {
        "category": "laptop",
        "name": "MacBook Air 13 M3",
        "price": 27990000,
        "color": "space_gray",
        "cpu": "Apple M3",
        "gpu": "Apple GPU 10-core",
        "ram": "8GB",
        "storage": "256GB SSD",
        "stock": 10,
        "image": "download_1.webp",
        "detail": "MacBook mỏng nhẹ, pin lâu, phù hợp học tập, văn phòng và thiết kế cơ bản.",
    },
    {
        "category": "laptop",
        "name": "MacBook Pro 14 M3 Pro",
        "price": 49990000,
        "color": "space_gray",
        "cpu": "Apple M3 Pro",
        "gpu": "Apple GPU 18-core",
        "ram": "18GB",
        "storage": "512GB SSD",
        "stock": 4,
        "image": "download_2.webp",
        "detail": "Laptop cao cấp cho lập trình, dựng video và xử lý tác vụ nặng.",
    },
    {
        "category": "laptop",
        "name": "HP Pavilion 15 Ryzen 5",
        "price": 13990000,
        "color": "silver",
        "cpu": "AMD Ryzen 5 7530U",
        "gpu": "AMD Radeon Graphics",
        "ram": "16GB",
        "storage": "512GB SSD",
        "stock": 12,
        "image": "download_1.webp",
        "detail": "Laptop học tập và văn phòng giá tốt, RAM 16GB chạy đa nhiệm ổn định.",
    },
    {
        "category": "dien-thoai",
        "name": "iPhone 15 Pro Max 256GB",
        "price": 30990000,
        "color": "gray",
        "cpu": "Apple A17 Pro",
        "gpu": "Apple GPU",
        "ram": "8GB",
        "storage": "256GB",
        "stock": 9,
        "image": "download_2.webp",
        "detail": "Điện thoại flagship Apple, camera mạnh, khung titan, hiệu năng cao.",
    },
    {
        "category": "dien-thoai",
        "name": "Samsung Galaxy S24 Ultra",
        "price": 26990000,
        "color": "black",
        "cpu": "Snapdragon 8 Gen 3",
        "gpu": "Adreno 750",
        "ram": "12GB",
        "storage": "256GB",
        "stock": 7,
        "image": "download_1.webp",
        "detail": "Flagship Android với bút S Pen, camera zoom xa và màn hình sắc nét.",
    },
    {
        "category": "dien-thoai",
        "name": "Xiaomi Redmi Note 13 128GB",
        "price": 4590000,
        "color": "blue",
        "cpu": "Snapdragon 685",
        "gpu": "Adreno 610",
        "ram": "8GB",
        "storage": "128GB",
        "stock": 25,
        "image": "download_2.webp",
        "detail": "Điện thoại giá dưới 5 triệu, màn hình đẹp, pin tốt, phù hợp học sinh sinh viên.",
    },
    {
        "category": "linh-kien-pc",
        "name": "Intel Core i9-14900K",
        "price": 14990000,
        "color": "black",
        "cpu": "Intel Core i9-14900K",
        "gpu": "",
        "ram": "",
        "storage": "",
        "stock": 5,
        "image": "download_1.webp",
        "detail": "CPU desktop cao cấp cho gaming, render và workstation.",
    },
    {
        "category": "linh-kien-pc",
        "name": "AMD Ryzen 7 7800X3D",
        "price": 10990000,
        "color": "gray",
        "cpu": "AMD Ryzen 7 7800X3D",
        "gpu": "",
        "ram": "",
        "storage": "",
        "stock": 6,
        "image": "download_2.webp",
        "detail": "CPU gaming nổi bật với 3D V-Cache, hiệu năng chơi game rất tốt.",
    },
    {
        "category": "linh-kien-pc",
        "name": "NVIDIA GeForce RTX 4070 12GB",
        "price": 16990000,
        "color": "black",
        "cpu": "",
        "gpu": "NVIDIA RTX 4070 12GB",
        "ram": "",
        "storage": "",
        "stock": 4,
        "image": "download_1.webp",
        "detail": "Card đồ họa mạnh cho gaming 2K, dựng hình và AI cơ bản.",
    },
    {
        "category": "linh-kien-pc",
        "name": "ASUS Dual RTX 3060 12GB",
        "price": 7990000,
        "color": "black",
        "cpu": "",
        "gpu": "NVIDIA RTX 3060 12GB",
        "ram": "",
        "storage": "",
        "stock": 11,
        "image": "download_2.webp",
        "detail": "GPU tầm trung giá tốt cho gaming Full HD và thiết kế đồ họa.",
    },
    {
        "category": "phu-kien",
        "name": "Logitech G502 X",
        "price": 1590000,
        "color": "white",
        "cpu": "",
        "gpu": "",
        "ram": "",
        "storage": "",
        "stock": 30,
        "image": "download_1.webp",
        "detail": "Chuột gaming công thái học, cảm biến chính xác, nhiều nút tùy chỉnh.",
    },
    {
        "category": "phu-kien",
        "name": "Keychron K2 Wireless",
        "price": 2290000,
        "color": "gray",
        "cpu": "",
        "gpu": "",
        "ram": "",
        "storage": "",
        "stock": 18,
        "image": "download_2.webp",
        "detail": "Bàn phím cơ không dây layout gọn, phù hợp làm việc và lập trình.",
    },
    {
        "category": "phu-kien",
        "name": "Sony WH-1000XM5",
        "price": 7490000,
        "color": "black",
        "cpu": "",
        "gpu": "",
        "ram": "",
        "storage": "",
        "stock": 9,
        "image": "download_1.webp",
        "detail": "Tai nghe chống ồn cao cấp, âm thanh tốt, pin lâu.",
    },
]


def reset_old_data():
    ChatHistory.objects.all().delete()
    ShippingAddress.objects.all().delete()
    Invoice.objects.all().delete()
    OrderItem.objects.all().delete()
    Order.objects.all().delete()
    Product.objects.all().delete()
    Category.objects.all().delete()


def create_categories():
    categories = {
        "laptop": "Laptop",
        "dien-thoai": "Điện thoại",
        "linh-kien-pc": "Linh kiện PC",
        "phu-kien": "Phụ kiện",
    }

    return {
        slug: Category.objects.create(name=name, slug=slug, is_sub=False)
        for slug, name in categories.items()
    }


def create_products(categories):
    products = []
    for data in TECH_PRODUCTS:
        category = categories[data.pop("category")]
        product = Product.objects.create(
            name=data["name"],
            price=Decimal(data["price"]),
            digital=False,
            image=data["image"],
            detail=data["detail"],
            color=data["color"],
            cpu=data["cpu"],
            gpu=data["gpu"],
            ram=data["ram"],
            storage=data["storage"],
            stock=data["stock"],
        )
        product.category.add(category)
        products.append(product)

    return products


def create_demo_admin_and_orders(products):
    admin, created = User.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@danangstore.local",
            "first_name": "Tinh",
            "last_name": "Store Admin",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    admin.is_staff = True
    admin.is_superuser = True
    admin.set_password("admin123")
    admin.save()

    customer, created = User.objects.get_or_create(
        username="khachhang",
        defaults={
            "email": "customer@danangstore.local",
            "first_name": "Khach",
            "last_name": "Hang",
        },
    )
    customer.set_password("khach123")
    customer.save()

    demo_orders = [
        ("approved", [(products[0], 1), (products[12], 2)]),
        ("approved", [(products[7], 2), (products[13], 1)]),
        ("pending", [(products[1], 1)]),
        ("canceled", [(products[14], 1)]),
    ]

    for status, items in demo_orders:
        order = Order.objects.create(
            customer=customer,
            complete=True,
            status=status,
            transaction_id=f"DEMO-{timezone.now().timestamp():.0f}",
            approved_date=timezone.now() if status == "approved" else None,
        )
        for product, quantity in items:
            OrderItem.objects.create(order=order, product=product, quantity=quantity)
            product.stock = max(product.stock - quantity, 0)
            product.save(update_fields=["stock"])

        if status == "approved":
            Invoice.objects.create(
                order=order,
                customer=customer,
                total_amount=order.get_cart_total,
            )

    return admin


def main():
    reset_old_data()
    categories = create_categories()
    products = create_products(categories)
    admin = create_demo_admin_and_orders(products)

    print("Da xoa du lieu cu 2024-2025 va nap du lieu cong nghe moi.")
    print(f"Danh muc: {Category.objects.count()}")
    print(f"San pham: {Product.objects.count()}")
    print(f"Don hang demo: {Order.objects.count()}")
    print(f"Hoa don demo: {Invoice.objects.count()}")
    print(f"Admin: {admin.username} / admin123")


if __name__ == "__main__":
    main()
