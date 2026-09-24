from dataclasses import dataclass
from fastapi import WebSocket


@dataclass(eq=False)
class Conn:
    ws: WebSocket
    # None  -> "global" socket: receives events for every chat of the user
    # int   -> legacy per-chat socket (/ws/{chat_id}): only that chat's events
    chat_id: int | None = None


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: dict[int, list[Conn]] = {}

    def connect(self, user_id: int, ws: WebSocket, chat_id: int | None = None) -> bool:
        """Register a socket. Returns True if the user just came online."""
        conns = self._conns.setdefault(user_id, [])
        first = not conns
        conns.append(Conn(ws, chat_id))
        return first

    def disconnect(self, user_id: int, ws: WebSocket) -> bool:
        """Remove a socket. Returns True if that was the user's last one."""
        conns = self._conns.get(user_id)
        if not conns:
            return False
        remaining = [c for c in conns if c.ws is not ws]
        if len(remaining) == len(conns):
            return False
        if remaining:
            self._conns[user_id] = remaining
            return False
        del self._conns[user_id]
        return True

    def is_online(self, user_id: int) -> bool:
        return bool(self._conns.get(user_id))

    def online_ids(self) -> set[int]:
        return set(self._conns)

    @staticmethod
    def _wants(conn: Conn, chat_id: int | None) -> bool:
        return chat_id is None or conn.chat_id is None or conn.chat_id == chat_id

    def is_watching(self, user_id: int, chat_id: int) -> bool:
        """Would a message for this chat reach the user right now?"""
        return any(self._wants(c, chat_id) for c in self._conns.get(user_id, []))

    async def send_to_user(self, user_id: int, payload: dict, chat_id: int | None = None) -> int:
        """Send to all of the user's sockets interested in chat_id. Returns how many succeeded."""
        sent = 0
        for conn in list(self._conns.get(user_id, [])):
            if not self._wants(conn, chat_id):
                continue
            try:
                await conn.ws.send_json(payload)
                sent += 1
            except Exception:
                # dead socket: its receive loop / idle timeout will clean it up
                pass
        return sent