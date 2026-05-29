import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from app.models import Category, Product


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
        "detail": "Laptop gaming manh me cho game thu, tan nhiet tot va man hinh tan so quet cao.",
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
        "detail": "Ultrabook cao cap, mong nhe, phu hop lam viec van phong va sang tao noi dung.",
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
        "detail": "Dien thoai flagship Apple, camera manh, khung titan, hieu nang cao.",
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
        "detail": "Flagship Android voi S Pen, camera zoom xa va man hinh sac net.",
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
        "detail": "Card do hoa manh cho gaming 2K, dung hinh va AI co ban.",
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
        "detail": "Chuot gaming cong thai hoc, cam bien chinh xac, nhieu nut tuy chinh.",
    },
]


class Command(BaseCommand):
    help = "Create an optional admin account and seed sample shop data for Render."

    def handle(self, *args, **options):
        self.create_admin()

        if self.env_bool("SEED_SAMPLE_DATA", default=False):
            self.seed_sample_data()
        else:
            self.stdout.write("Sample data seeding skipped. Set SEED_SAMPLE_DATA=True to enable it.")

    def create_admin(self):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "admin").strip()
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "").strip()

        if not password:
            self.stdout.write("Admin user skipped because DJANGO_SUPERUSER_PASSWORD is not set.")
            return

        user, created = User.objects.get_or_create(username=username)
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} admin user: {username}"))

    def seed_sample_data(self):
        categories = {
            "laptop": "Laptop",
            "dien-thoai": "Dien thoai",
            "linh-kien-pc": "Linh kien PC",
            "phu-kien": "Phu kien",
        }

        category_map = {}
        for slug, name in categories.items():
            category, _ = Category.objects.update_or_create(
                slug=slug,
                defaults={"name": name, "is_sub": False},
            )
            category_map[slug] = category

        for item in TECH_PRODUCTS:
            category = category_map[item["category"]]
            product, _ = Product.objects.update_or_create(
                name=item["name"],
                defaults={
                    "price": Decimal(item["price"]),
                    "digital": False,
                    "image": item["image"],
                    "detail": item["detail"],
                    "color": item["color"],
                    "cpu": item["cpu"],
                    "gpu": item["gpu"],
                    "ram": item["ram"],
                    "storage": item["storage"],
                    "stock": item["stock"],
                },
            )
            product.category.set([category])

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Category.objects.count()} categories and {Product.objects.count()} products."
            )
        )

    @staticmethod
    def env_bool(name, default=False):
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in ("1", "true", "yes", "on")
