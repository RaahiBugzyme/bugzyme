from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str

class UserUpdate(BaseModel):
    username: str

class UserLogin(BaseModel):
    username: str
    password: str