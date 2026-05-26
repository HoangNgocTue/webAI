# Generated manually for checkout shipping address improvements.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0009_product_cpu_product_gpu_product_ram_product_stock_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shippingaddress',
            name='mobile',
            field=models.CharField(max_length=15, null=True),
        ),
    ]
