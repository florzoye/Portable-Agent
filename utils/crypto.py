import os
from cryptography.fernet import Fernet, InvalidToken

class TokenCipher:
    def __init__(self):
        raw_key = os.environ.get("TOKEN_ENCRYPTION_KEY")
        if not raw_key:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY is required. Generate it with: "
                "python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        try:
            self._fernet = Fernet(raw_key.strip().encode())
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY must be a valid Fernet key. Generate it with: "
                "python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            ) from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            raise ValueError("Error for decrypt token")

    def encrypt_optional(self, value: str | None) -> str | None:
        return self.encrypt(value) if value is not None else None

    def decrypt_optional(self, value: str | None) -> str | None:
        return self.decrypt(value) if value is not None else None