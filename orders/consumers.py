from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .realtime import KITCHEN_GROUP


class KitchenConsumer(AsyncJsonWebsocketConsumer):
    """Live order feed for the kitchen display system."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not getattr(user, "is_staff_member", False):
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(KITCHEN_GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected", "message": "Kitchen channel live"})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(KITCHEN_GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        if action == "ping":
            await self.send_json({"type": "pong"})

    # ---- group event handlers -------------------------------------------
    async def order_update(self, event):
        await self.send_json({"type": "order.update", "order": event["order"]})
