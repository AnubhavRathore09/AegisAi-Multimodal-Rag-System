from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models.user import users_db
from src.services.auth_service import hash_password

router = APIRouter()


class User(BaseModel):
    username: str
    password: str


# 🔥 SIGNUP API
@router.post("/signup")
def signup(user: User):

    # ❌ agar already user hai
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="User already exists")

    # 🔐 password hash
    hashed_password = hash_password(user.password)

    # 💾 store user
    users_db[user.username] = {
        "username": user.username,
        "password": hashed_password
    }

    return {
        "message": "User created successfully"
    }
