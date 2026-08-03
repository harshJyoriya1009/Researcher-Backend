from pydantic import EmailStr

from app.schemas.common import TimestampedSchema


class UserRead(TimestampedSchema):
    name: str
    email: EmailStr
    is_active: bool
    is_verified: bool
    default_model: str
