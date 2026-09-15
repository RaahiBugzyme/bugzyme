from fastapi import WebSocket


class ConnectionManager:

    def __init__(self):
        # One user can have multiple WebSocket connections.
        # Each connection is tied to one specific chat.
        # user_id -> [(chat_id, websocket), ...]
        self.active_connections: dict[int, list[tuple[int, WebSocket]]] = {}

    async def connect(
        self,
        user_id: int,
        chat_id: int,
        websocket: WebSocket
    ):
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        self.active_connections[user_id].append(
            (chat_id, websocket)
        )

    def disconnect(
        self,
        user_id: int,
        chat_id: int,
        websocket: WebSocket
    ):
        connections = self.active_connections.get(user_id)

        if not connections:
            return

        self.active_connections[user_id] = [
            (connected_chat_id, connected_websocket)
            for connected_chat_id, connected_websocket in connections
            if connected_websocket is not websocket
        ]

        if not self.active_connections[user_id]:
            del self.active_connections[user_id]

    def is_online(self, user_id: int) -> bool:
        return bool(self.active_connections.get(user_id))

    def is_online_in_chat(self, user_id: int, chat_id: int) -> bool:
        return any(
            connected_chat_id == chat_id
            for connected_chat_id, _ in self.active_connections.get(
                user_id, []
            )
        )

    async def send_personal_message(
        self,
        message,
        user_id: int,
        chat_id: int
    ):
        connections = self.active_connections.get(user_id, [])

        for connected_chat_id, websocket in connections.copy():
            if connected_chat_id != chat_id:
                continue

            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(
                    user_id,
                    connected_chat_id,
                    websocket
                )

    async def notify_presence(
        self,
        user_id: int,
        status: str,
        receiver_id: int,
        chat_id: int
    ):
        connections = self.active_connections.get(receiver_id, [])

        for connected_chat_id, websocket in connections.copy():
            if connected_chat_id != chat_id:
                continue

            try:
                await websocket.send_json({
                    "type": "presence",
                    "user_id": user_id,
                    "status": status
                })
            except Exception:
                self.disconnect(
                    receiver_id,
                    connected_chat_id,
                    websocket
                )