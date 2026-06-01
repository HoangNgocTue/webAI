from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from app.models import Category, Order, OrderItem, Product


@override_settings(SECURE_SSL_REDIRECT=False)
class ChatbotCartIntentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="buyer", password="secret")
        self.client.force_login(self.user)
        self.category = Category.objects.create(name="Laptop", slug="laptop")

        self.s24 = self.create_product("Samsung Galaxy S24 Ultra", 26990000)
        self.strix = self.create_product("ASUS ROG Strix G16 RTX 4060", 29990000)
        self.zephyrus = self.create_product("ASUS ROG Zephyrus G14", 27990000)

    def create_product(self, name, price):
        product = Product.objects.create(name=name, price=price, stock=5)
        product.category.add(self.category)
        return product

    def post_chat(self, message):
        with patch("chatbot.views.get_ai_intent", return_value={}):
            return self.client.post("/chatbot/api/", {"message": message})

    def test_cart_view_does_not_add_context_product(self):
        order = Order.objects.create(customer=self.user, complete=False)
        OrderItem.objects.create(order=order, product=self.s24, quantity=1)
        session = self.client.session
        session["chatbot_last_product_ids"] = [self.strix.id]
        session["chatbot_last_added_product_id"] = self.strix.id
        session.save()

        response = self.post_chat("gio hang")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Gi\u1ecf h\u00e0ng hi\u1ec7n t\u1ea1i", response.json()["reply"])
        self.assertEqual(OrderItem.objects.get(order=order, product=self.s24).quantity, 1)
        self.assertFalse(OrderItem.objects.filter(order=order, product=self.strix).exists())

    def test_add_product_by_index_still_adds_to_cart(self):
        session = self.client.session
        session["chatbot_last_product_ids"] = [self.s24.id]
        session.save()

        response = self.post_chat("them san pham 1 vao gio hang")

        self.assertContains(response, self.s24.name, status_code=200)
        self.assertEqual(OrderItem.objects.get(product=self.s24, order__customer=self.user).quantity, 1)

    def test_remove_cart_product_requires_confirmation_and_can_switch_candidate(self):
        order = Order.objects.create(customer=self.user, complete=False)
        first_item = OrderItem.objects.create(order=order, product=self.zephyrus, quantity=1)
        second_item = OrderItem.objects.create(order=order, product=self.strix, quantity=1)

        response = self.post_chat("xóa ASUS ROG")
        self.assertContains(response, self.zephyrus.name, status_code=200)
        self.assertTrue(OrderItem.objects.filter(id=first_item.id).exists())
        self.assertTrue(OrderItem.objects.filter(id=second_item.id).exists())

        response = self.post_chat("ko phai")
        self.assertContains(response, self.strix.name, status_code=200)

        response = self.post_chat("dung")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"\u0110\u00e3 x\u00f3a **{self.strix.name}**", response.json()["reply"])
        self.assertTrue(OrderItem.objects.filter(id=first_item.id).exists())
        self.assertFalse(OrderItem.objects.filter(id=second_item.id).exists())
