from fastapi import status


class GraphboardError(Exception):
    """Base class for all Graphboard exceptions."""

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(GraphboardError):
    """Raised when validation fails."""

    pass
