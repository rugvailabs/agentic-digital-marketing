"""Image rendering registry."""

from app.images.base import SIZES, ImageBrief, ImageProvider, RenderedImage
from app.images.fonts import load_font, script_of, shaping_available
from app.images.gemini_image import GeminiImageProvider
from app.images.pillow import TEMPLATES, PillowTemplateProvider

__all__ = [
    "SIZES",
    "TEMPLATES",
    "GeminiImageProvider",
    "ImageBrief",
    "ImageProvider",
    "PillowTemplateProvider",
    "RenderedImage",
    "load_font",
    "script_of",
    "shaping_available",
]
