from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


class ShoppingDataStore:
    """Loads mock JSON once and builds in-memory indexes for fast lookups."""

    def __init__(self, json_path: Path) -> None:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.metadata = data.get("metadata", {})
        customers: list[dict] = data.get("customers", [])
        orders: list[dict] = data.get("orders", [])
        vouchers: list[dict] = data.get("vouchers", [])

        self.customer_by_id: dict[str, Any] = {
            str(c["customer_id"]): c for c in customers
        }
        self.order_by_id: dict[str, Any] = {
            str(o["order_id"]): o for o in orders
        }
        self.orders_by_customer_id: dict[str, list[Any]] = {}
        for order in orders:
            cid = str(order.get("customer_id", ""))
            self.orders_by_customer_id.setdefault(cid, []).append(order)

        self.vouchers_by_customer_id: dict[str, list[Any]] = {}
        for voucher in vouchers:
            cid = str(voucher.get("customer_id", ""))
            self.vouchers_by_customer_id.setdefault(cid, []).append(voucher)

    def get_customer_by_id(self, customer_id: str) -> dict[str, Any]:
        customer = self.customer_by_id.get(str(customer_id))
        if customer is None:
            return {"status": "not_found", "customer_id": customer_id}
        return {"status": "ok", "customer": customer}

    def get_orders_by_customer_id(self, customer_id: str, limit: int = 10) -> dict[str, Any]:
        orders = self.orders_by_customer_id.get(str(customer_id))
        if orders is None:
            return {"status": "not_found", "customer_id": customer_id}
        recent = sorted(orders, key=lambda o: o.get("created_at", ""), reverse=True)[:limit]
        return {"status": "ok", "customer_id": customer_id, "orders": recent}

    def get_order_detail_by_order_id(self, order_id: str) -> dict[str, Any]:
        order = self.order_by_id.get(str(order_id))
        if order is None:
            return {"status": "not_found", "order_id": order_id}
        return {"status": "ok", "order": order}

    def get_vouchers_by_customer_id(
        self,
        customer_id: str,
        only_active: bool = False,
    ) -> dict[str, Any]:
        vouchers = self.vouchers_by_customer_id.get(str(customer_id))
        if vouchers is None:
            return {"status": "not_found", "customer_id": customer_id}
        if only_active:
            vouchers = [
                v for v in vouchers
                if v.get("status") in ("active", "restored") and v.get("remaining_uses", 0) > 0
            ]
        return {"status": "ok", "customer_id": customer_id, "vouchers": vouchers}


def build_data_tools(store: ShoppingDataStore) -> list:
    @tool
    def get_customer_by_id(customer_id: str) -> str:
        """Lấy thông tin khách hàng theo customer_id (ví dụ: C001).
        Trả về tên, tier, quota voucher còn lại trong tháng."""
        return json.dumps(store.get_customer_by_id(customer_id), ensure_ascii=False)

    @tool
    def get_orders_by_customer_id(customer_id: str) -> str:
        """Lấy danh sách đơn hàng gần nhất của khách hàng theo customer_id (ví dụ: C001).
        Trả về danh sách đơn gần nhất kèm trạng thái."""
        return json.dumps(store.get_orders_by_customer_id(customer_id), ensure_ascii=False)

    @tool
    def get_order_detail_by_order_id(order_id: str) -> str:
        """Lấy chi tiết một đơn hàng theo order_id (ví dụ: 1971, 2058).
        Trả về trạng thái đơn, ngày giao dự kiến, thông tin hoàn trả (can_return_now, eligible_for_return_until)."""
        return json.dumps(store.get_order_detail_by_order_id(order_id), ensure_ascii=False)

    @tool
    def get_vouchers_by_customer_id(customer_id: str) -> str:
        """Lấy danh sách tất cả voucher của khách hàng theo customer_id (ví dụ: C001).
        Trả về danh sách voucher kèm trạng thái, remaining_uses, giá trị giảm giá."""
        return json.dumps(store.get_vouchers_by_customer_id(customer_id), ensure_ascii=False)

    return [
        get_customer_by_id,
        get_orders_by_customer_id,
        get_order_detail_by_order_id,
        get_vouchers_by_customer_id,
    ]
