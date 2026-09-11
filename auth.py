from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv # tells auth.py to read secret key from .env instead of hardcoding it
import os # tells auth.py to read secret key from .env instead of hardcoding it

load_dotenv() # tells auth.py to read secret key from .env instead of hardcoding it

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY") # tells auth.py to read secret key from .env instead of hardcoding it
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 #24 hours

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update ({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError
from database import get_db
import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
bearer_scheme = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: Session = Depends(get_db)):
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials"
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception

    return user

def require_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

def require_super_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin" or not current_user.is_super_admin:
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current_user