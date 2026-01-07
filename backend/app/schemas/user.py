from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    telegram_user_id: str
    telegram_username: str | None = None
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    locale: str | None = None

class UserOut(BaseModel):
    id: str
    telegram_user_id: str
    telegram_username: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    locale: str | None = None

    class Config:
        from_attributes = True
