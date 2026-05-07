"""
Service modules for the dependiq application
"""

from .analysis_service import run_analysis
from .dependency_agent import (
    extract_dependencies_with_gpt,
    identify_artifacts_with_gpt,
    research_latest_versions,
    update_dependency_file_with_gpt,
    update_entire_project_with_gpt,
    update_entire_project_with_gpt_with_progress,
)
from .progress_service import (
    get_analysis_status,
    get_progress_status,
    update_analysis_progress,
    update_progress,
)
from .update_service import run_update

__all__ = [
    "extract_dependencies_with_gpt",
    "get_analysis_status",
    "get_progress_status",
    "identify_artifacts_with_gpt",
    "research_latest_versions",
    "run_analysis",
    "run_update",
    "update_analysis_progress",
    "update_dependency_file_with_gpt",
    "update_entire_project_with_gpt",
    "update_entire_project_with_gpt_with_progress",
    "update_progress",
]
