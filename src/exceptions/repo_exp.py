from src.exceptions.base import AppException

class RepositoryException(AppException):
    def __init__(self, message: str, entity: str = None, original_error: Exception = None, **kwargs):
        self.entity = entity
        self.original_error = original_error
        details = kwargs.get('details', {})
        if entity:
            details['entity'] = entity
        if original_error:
            details['original_error'] = str(original_error)
        super().__init__(message, **kwargs, details=details)


class UserRepositoryException(RepositoryException):
    def __init__(self, message: str = "Ошибка репозитория пользователей", original_error: Exception = None):
        super().__init__(
            message=message,
            entity="user",
            original_error=original_error,
            status_code=500
        )


class TokenRepositoryException(RepositoryException):
    def __init__(self, message: str = "Ошибка репозитория токенов", original_error: Exception = None):
        super().__init__(
            message=message,
            entity="token",
            original_error=original_error,
            status_code=500
        )


class UserNotFoundException(RepositoryException):
    def __init__(self, user_id: int = None, tg_id: int = None, message: str = "Пользователь не найден"):
        details = {}
        if user_id:
            details['user_id'] = user_id
        if tg_id:
            details['tg_id'] = tg_id
        super().__init__(
            message=message,
            entity="user",
            status_code=404,
            details=details
        )


class TokenNotFoundException(RepositoryException):
    def __init__(self, user_id: int = None, message: str = "Токен не найден"):
        details = {'user_id': user_id} if user_id else {}
        super().__init__(
            message=message,
            entity="token",
            status_code=404,
            details=details
        )
