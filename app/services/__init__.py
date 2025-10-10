"""
Service modules for the dependiq application
"""

from .ai_service import (
    extract_dependencies_with_gpt,
    identify_artifacts_with_gpt,
    research_latest_versions_with_gpt,
    update_dependency_file_with_gpt,
    update_entire_project_with_gpt,
    update_entire_project_with_gpt_with_progress,
    validate_and_fix_code_with_gpt,
)
from .progress_service import (
    get_analysis_status,
    get_progress_status,
    update_analysis_progress,
    update_progress,
)

__all__ = [
    "extract_dependencies_with_gpt",
    "get_analysis_status",
    "get_progress_status",
    "identify_artifacts_with_gpt",
    "research_latest_versions_with_gpt",
    "update_analysis_progress",
    "update_dependency_file_with_gpt",
    "update_entire_project_with_gpt",
    "update_entire_project_with_gpt_with_progress",
    "update_progress",
    "validate_and_fix_code_with_gpt",
]
