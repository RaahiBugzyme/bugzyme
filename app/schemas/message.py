from pydantic import BaseModel


class MessageCreate(BaseModel):
    conversation_id: int
    content: str