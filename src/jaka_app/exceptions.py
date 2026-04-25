class JakaApiError(RuntimeError):
    """Raised when jkrc returns a non-zero error code."""

    def __init__(self, message: str, ret: int | None = None, method: str | None = None):
        self.ret = ret
        self.method = method
        super().__init__(message)


class JakaNotInstalledError(ImportError):
    """Raised when the `jkrc` module is not available."""
