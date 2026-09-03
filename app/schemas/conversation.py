from pydantic import BaseModel


class ConversationCreate(BaseModel):
    user_id: int