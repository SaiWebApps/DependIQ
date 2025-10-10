"""
Dependency data model
"""

from dataclasses import dataclass


@dataclass
class Dependency:
    """Represents a project dependency with current and latest version information."""

    name: str
    current_version: str
    latest_version: str = ""
    description: str = ""
