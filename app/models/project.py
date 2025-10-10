"""
Project type definitions and file extension mappings
"""

from enum import Enum
from typing import ClassVar


class ProjectType(Enum):
    """Supported project types with their characteristics."""

    PYTHON = "python"
    MAVEN = "maven"
    GRADLE = "gradle"
    SBT = "sbt"
    UNKNOWN = "unknown"


class FileExtensionMap:
    """Mapping of file extensions to their corresponding language types."""

    SOURCE_EXTENSIONS: ClassVar[dict[ProjectType, list[str]]] = {
        ProjectType.PYTHON: [".py"],
        ProjectType.MAVEN: [".java", ".scala"],
        ProjectType.GRADLE: [".java", ".scala"],
        ProjectType.SBT: [".scala", ".java"],
    }

    ANALYZABLE_EXTENSIONS: ClassVar[set[str]] = {
        ".scala",
        ".java",
        ".py",
        ".sbt",
        ".gradle",
        ".kts",
        ".xml",
        ".conf",
        ".properties",
        ".yml",
        ".yaml",
        ".json",
        ".md",
        ".txt",
        ".sh",
        ".bat",
    }

    SYNTAX_LANGUAGE_MAP: ClassVar[dict[str, str]] = {
        ".scala": "scala",
        ".java": "java",
        ".py": "python",
        ".sbt": "scala",
        ".gradle": "groovy",
        ".xml": "xml",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".conf": "properties",
        ".properties": "properties",
    }
