"""A small starting test suite for the order desk."""

from pathlib import Path
import tempfile
import unittest

from supplydesk.service import OrderService


class OrderSmokeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def test_regular_pickup_quote(self):
        quote = self.service.quote("regular", [{"product_id": "notebook", "quantity": 2}])
        self.assertEqual(quote["subtotal_cents"], 1000)
        self.assertEqual(quote["discount_cents"], 0)
        self.assertEqual(quote["delivery_cents"], 0)
        self.assertEqual(quote["total_cents"], 1000)

    def test_student_delivery_quote(self):
        quote = self.service.quote("student", [{"product_id": "hoodie", "quantity": 2}], "delivery")
        self.assertEqual(quote["discount_cents"], 800)
        self.assertEqual(quote["delivery_cents"], 600)
        self.assertEqual(quote["total_cents"], 7800)

    def test_order_can_be_reopened(self):
        order = self.service.place_order("regular", [{"product_id": "mug", "quantity": 1}])
        self.assertEqual(order["order_id"], "ORD-0001")
        self.assertEqual(order["status"], "placed")
        self.assertEqual(OrderService(self.path).get_order(order["order_id"]), order)

    def test_cancel_order_restores_stock(self):
        before = self.service.catalog()
        order = self.service.place_order("regular", [{"product_id": "pen-pack", "quantity": 2}])
        cancelled = self.service.cancel_order(order["order_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.service.catalog(), before)

        # Normal behavior
    def test_regular_delivery_above_free_delivery_threshold(self):
        quote = self.service.quote(
            "regular",
            [{"product_id": "hoodie", "quantity": 3}],
            "delivery"
        )

        self.assertEqual(quote["subtotal_cents"], 12000)
        self.assertEqual(quote["discount_cents"], 0)
        self.assertEqual(quote["delivery_cents"], 0)
        self.assertEqual(quote["total_cents"], 12000)

    # Boundary Behaviour 
    def test_student_discount_applies_at_exactly_5000_cents(self):
        quote = self.service.quote(
            "student",
            [
                {"product_id": "hoodie", "quantity": 1},
                {"product_id": "notebook", "quantity": 2}
            ]
        )

        self.assertEqual(quote["subtotal_cents"], 5000)
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["total_cents"], 4500)

    # Invalid Behaviour
    def test_invalid_quantity_does_not_change_saved_state(self):
        before_catalog = self.service.catalog()
        before_orders = self.service.list_orders()

        with self.assertRaises(ValueError):
            self.service.place_order(
                "regular",
                [{"product_id": "notebook", "quantity": 0}]
            )

        self.assertEqual(self.service.catalog(), before_catalog)
        self.assertEqual(self.service.list_orders(), before_orders)

    def test_duplicate_lines_cannot_exceed_available_stock(self):
        before_catalog = self.service.catalog()

        with self.assertRaises(ValueError):
            self.service.place_order(
                "regular",
                [
                    {"product_id": "hoodie", "quantity": 3},
                    {"product_id": "hoodie", "quantity": 3}
                ]
            )

        self.assertEqual(self.service.catalog(), before_catalog)
        self.assertEqual(self.service.list_orders(), [])

    # Behaviour to perserve
    def test_quote_matches_placed_order_and_does_not_reserve_stock(self):
        items = [{"product_id": "notebook", "quantity": 2}]

        before_catalog = self.service.catalog()

        quote = self.service.quote("regular", items)

        self.assertEqual(self.service.catalog(), before_catalog)
        self.assertEqual(self.service.list_orders(), [])

        order = self.service.place_order("regular", items)

        self.assertEqual(order["subtotal_cents"], quote["subtotal_cents"])
        self.assertEqual(order["discount_cents"], quote["discount_cents"])
        self.assertEqual(order["delivery_cents"], quote["delivery_cents"])
        self.assertEqual(order["total_cents"], quote["total_cents"])
        self.assertEqual(order["items"], quote["items"])

    def test_cancelling_order_twice_restores_stock_only_once(self):
        order = self.service.place_order(
            "regular",
            [{"product_id": "pen-pack", "quantity": 2}]
        )

        self.service.cancel_order(order["order_id"])
        stock_after_first_cancellation = self.service.catalog()

        cancelled = self.service.cancel_order(order["order_id"])

        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.service.catalog(), stock_after_first_cancellation)

    def test_regular_express_quote(self):
        quote = self.service.quote(
            "regular",
            [{"product_id": "notebook", "quantity": 2}],
            "express",
        )

        self.assertEqual(1000, quote["subtotal_cents"])
        self.assertEqual(0, quote["discount_cents"])
        self.assertEqual(1200, quote["delivery_cents"])
        self.assertEqual(2200, quote["total_cents"])


    def test_student_express_quote(self):
        quote = self.service.quote(
            "student",
            [{"product_id": "hoodie", "quantity": 2}],
            "express",
        )

        self.assertEqual(8000, quote["subtotal_cents"])
        self.assertEqual(800, quote["discount_cents"])
        self.assertEqual(1200, quote["delivery_cents"])
        self.assertEqual(8400, quote["total_cents"])


    def test_express_delivery_is_charged_above_free_delivery_threshold(self):
        quote = self.service.quote(
            "regular",
            [{"product_id": "hoodie", "quantity": 3}],
            "express",
        )

        self.assertEqual(12000, quote["subtotal_cents"])
        self.assertEqual(1200, quote["delivery_cents"])
        self.assertEqual(13200, quote["total_cents"])


    def test_express_quote_matches_placed_and_reopened_order(self):
        items = [{"product_id": "hoodie", "quantity": 2}]

        quote = self.service.quote("student", items, "express")
        order = self.service.place_order("student", items, "express")

        for field in (
            "customer_type",
            "fulfillment",
            "items",
            "subtotal_cents",
            "discount_cents",
            "delivery_cents",
            "total_cents",
        ):
            self.assertEqual(quote[field], order[field])

        reopened_service = OrderService(self.path)
        reopened_order = reopened_service.get_order(order["order_id"])

        self.assertEqual("express", reopened_order["fulfillment"])
        self.assertEqual(800, reopened_order["discount_cents"])
        self.assertEqual(1200, reopened_order["delivery_cents"])
        self.assertEqual(8400, reopened_order["total_cents"])
        self.assertEqual(items[0]["quantity"], reopened_order["items"][0]["quantity"])


    def test_invalid_fulfillment_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.quote(
                "regular",
                [{"product_id": "notebook", "quantity": 2}],
                "overnight",
            )


if __name__ == "__main__":
    unittest.main()
