"""Helpers for broadcasting realtime order updates to the kitchen display."""

from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

KITCHEN_GROUP = "kitchen"

ACTIVE_STATUSES = [
    "pending",
    "confirmed",
    "preparing",
    "ready",
    "out_for_delivery",
]


def serialize_order(order) -> dict:
    items = [
        {
            "name": item.name,
            "quantity": item.quantity,
            "options": item.options or {},
        }
        for item in order.items.all()
    ]
    placed = order.placed_at or order.created_at
    return {
        "number": order.number,
        "customer": order.customer_name,
        "status": order.status,
        "status_display": order.get_status_display(),
        "fulfillment": order.get_fulfillment_display(),
        "fulfillment_key": order.fulfillment,
        "location": order.location.name if order.location else "",
        "note": order.note,
        "total": str(order.total),
        "items": items,
        "item_count": sum(i["quantity"] for i in items),
        "placed_at": placed.isoformat() if placed else None,
        "elapsed": int((timezone.now() - placed).total_seconds()) if placed else 0,
        "active": order.status in ACTIVE_STATUSES,
    }


def broadcast_order(order):
    """Send an order update to every connected kitchen display."""
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        KITCHEN_GROUP,
        {"type": "order.update", "order": serialize_order(order)},
    )
