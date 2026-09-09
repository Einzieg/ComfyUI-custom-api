class APIError(Exception):
    """Stable error codes for localized UI; details must be sanitized at the boundary."""

    def __init__(self, code, detail="", status=400):
        self.code = code
        self.detail = str(detail)
        self.status = status
        super().__init__(f"{code}: {self.detail}" if detail else code)

    def as_dict(self):
        return {"code": self.code, "detail": self.detail}
