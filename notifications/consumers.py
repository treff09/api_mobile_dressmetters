import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.group_name = f'user_{self.user_id}'

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        print(f"✅ WebSocket connecté pour l'utilisateur {self.user_id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def send_notification(self, event):
        # On récupère l'objet 'data' que tu as envoyé depuis la vue Django
        notification_data = event.get('data', {})
        
        # On l'envoie tel quel à Flutter
        # Flutter recevra : {"type": "NEW_ORDER", "title": "...", "message": "..."}
        await self.send(text_data=json.dumps(notification_data))
        print(f"📤 Notification envoyée à l'utilisateur {self.user_id}: {notification_data}")