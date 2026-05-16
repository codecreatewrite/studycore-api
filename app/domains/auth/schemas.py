from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    picture: str | None
    onboarding_completed: bool

    model_config = {"from_attributes": True}


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: UserResponse | None = None
