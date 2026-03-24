from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

def get_error_title(status_code: int) -> str:
    """Maps HTTP status codes to standardized error titles."""
    titles = {
        400: "Bad request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Resource not found",
        413: "Payload too large",
        429: "Too many requests",
        500: "Internal server error"
    }
    return titles.get(status_code, "An error occurred")

def setup_exception_handlers(app: FastAPI):
    """
    Registers global exception handlers to standardize API error responses.
    """
    
    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Overrides default HTTP exceptions to use the standardized format."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": get_error_title(exc.status_code),
                "details": exc.detail
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
        Overrides FastAPI's default 422 validation errors to return a 400 Bad Request
        with a standardized, flattened detail string.
        """
        details = []
        for error in exc.errors():
            # e.g., "query -> limit: value is not a valid integer"
            loc = " -> ".join(str(l) for l in error.get("loc", []) if l not in ("body", "query", "path"))
            msg = error.get("msg", "")
            details.append(f"{loc}: {msg}" if loc else msg)
        
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad request",
                "details": "; ".join(details)
            }
        )