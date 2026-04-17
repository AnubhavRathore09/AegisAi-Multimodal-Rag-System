from passlib.context import CryptContext

# 🔐 bcrypt hashing setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# 🔥 Hash password
def hash_password(password: str):
    return pwd_context.hash(password)


# 🔍 Verify password
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)
