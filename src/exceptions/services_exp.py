from src.exceptions.base import AppException

class ServiceException(AppException):
    def __init__(self, message: str, original_error: Exception = None, **kwargs):
        self.original_error = original_error
        details = kwargs.get('details', {})
        if original_error:
            details['original_error'] = str(original_error)
            details['original_error_type'] = original_error.__class__.__name__
        super().__init__(message, **kwargs, details=details)


class CalendarServiceException(ServiceException):
    def __init__(self, message: str = "Error Google Calendar services", original_error: Exception = None):
        super().__init__(
            message=message,
            original_error=original_error,
            status_code=500
        )


class CalendarAuthException(ServiceException):
    def __init__(self, message: str = "Google Calendar Authentication Error", original_error: Exception = None):
        super().__init__(
            message=message,
            original_error=original_error,
            status_code=401
        )


class CalendarTokenException(ServiceException):
    def __init__(self, message: str = "Error with the Google Calendar token", original_error: Exception = None):
        super().__init__(
            message=message,
            original_error=original_error,
            status_code=400
        )
