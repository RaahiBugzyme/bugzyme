from jose import jwt
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy.orm import Session

from passlib.context import CryptContext

from app.database.database import get_db
from app.database.models import User


# Secret key used to create and verify JWT tokens.
# In production, this should be stored in an environment variable.
SECRET_KEY = "bugzyme-secret-key"

# Algorithm used to sign the JWT token.
ALGORITHM = "HS256"



# JWT TOKEN CREATION


def create_access_token(data: dict):
    """
    Creates a JWT access token after successful login.
    """

    # Create a copy so the original data is not modified.
    to_encode = data.copy()

    # Set the token expiration time to 30 minutes from now.
    expire = datetime.utcnow() + timedelta(minutes=30)

    # Add the expiration time to the JWT payload.
    to_encode.update({"exp": expire})

    # Encode the payload and create the JWT token.
    token = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token



# PASSWORD HASHING


# Configure bcrypt for securely hashing passwords.
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def hash_password(password: str):
    """
    Converts a plain-text password into a secure hash.
    Used during user registration.
    """

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str):
    """
    Verifies whether the entered password
    matches the stored password hash.
    Used during login.
    """

    return pwd_context.verify(
        plain_password,
        hashed_password
    )



# JWT AUTHENTICATION


# Tells FastAPI that authentication uses a Bearer token.
#
# Example:
# Authorization: Bearer <JWT_TOKEN>
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/login"
)


def get_current_user(
    # Extract the JWT token from the Authorization header.
    token: str = Depends(oauth2_scheme),

    # Get a database session.
    db: Session = Depends(get_db)
):
    """
    Verifies the JWT token and returns the authenticated user.
    """

    try:

        # Decode the JWT and verify its signature.
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        # Extract the user ID from the JWT payload.
        user_id = payload.get("sub")

        # If the user ID is missing, the token is invalid.
        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

    except Exception:

        # Reject invalid, expired, or tampered tokens.
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    # Find the user in the database using the ID from the JWT.
    user = db.query(User).filter(
        User.id == int(user_id)
    ).first()

    # If the user does not exist, authentication fails.
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    # Return the authenticated User object.
    return user
