class ServiceError(Exception):
    status_code = 400


class NotFound(ServiceError):
    status_code = 404


class Forbidden(ServiceError):
    status_code = 403


class Conflict(ServiceError):
    status_code = 409


class RuleViolation(ServiceError):
    """A business rule blocks the action (e.g. a stock-in batch with unentered shared costs)."""

    status_code = 422
