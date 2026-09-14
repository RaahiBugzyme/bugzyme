from pydantic import BaseModel
from datetime import datetime


# Schema used when a user registers
class UserCreate(BaseModel):
    username: str
    email: str
    password: str


# Schema used when sending user data back to the client
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_online: bool
    last_seen: datetime | None

    class Config:
        from_attributes = True

# Schema used when a user logs in
class UserLogin(BaseModel):
    email: str
    password: str


class ChatCreate(BaseModel):
    user2_id: int
    

class MessageCreate(BaseModel):
    chat_id: int
    content: str