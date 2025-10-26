from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    wa_id: str
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    locale: str | None = None

class UserOut(BaseModel):
    id: str
    wa_id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    locale: str | None = None

    class Config:
        from_attributes = True
