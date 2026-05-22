import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webbanhang.settings')
django.setup()

from app.models import Product, Category

with open("db_info.txt", "w", encoding="utf-8") as f:
    f.write(f"Products count: {Product.objects.count()}\n")
    for p in Product.objects.all():
        cats = [c.name for c in p.category.all()]
        f.write(f"ID: {p.id} | Name: {p.name} | Price: {p.price} | Color: {p.color} | Detail: {p.detail} | Cats: {cats}\n")

    f.write(f"\nCategories count: {Category.objects.count()}\n")
    for c in Category.objects.all():
        f.write(f"ID: {c.id} | Name: {c.name} | Slug: {c.slug} | Is Sub: {c.is_sub}\n")
print("Done writing to db_info.txt")
