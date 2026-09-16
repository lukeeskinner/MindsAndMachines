"""Standalone course ingestion; imports never activate runtime integration."""
from .extraction import extract_material
from .models import IngestionError, ProcessedCourse
from .pipeline import process_course

__all__ = ["extract_material", "IngestionError", "ProcessedCourse", "process_course"]
