"""Custom exceptions for Agent Alpha."""

from __future__ import annotations


class AgentAlphaException(Exception):
    """Base exception for application-specific errors."""

    def __init__(
        self,
        message: str = "An error occurred",
        details: dict | None = None,
    ) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    @property
    def status_code(self) -> int:
        return 500


class NotFoundError(AgentAlphaException):
    """Raised when a requested resource does not exist."""

    @property
    def status_code(self) -> int:
        return 404


class BadRequestError(AgentAlphaException):
    """Raised when the request is invalid."""

    @property
    def status_code(self) -> int:
        return 400
