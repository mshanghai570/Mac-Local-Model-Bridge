from .rest import router as rest_router
from .openai_compat import openai_router

__all__ = ["rest_router", "openai_router"]
