"""
Project type detection and source file utilities
"""

import os


def detect_project_type(tmpdir: str) -> tuple[str, str, str]:
    """Detect project type and return (project_type, dependency_file_path, dependency_file_name)"""
    for root, dirs, files in os.walk(tmpdir):
        depth = root[len(tmpdir) :].count(os.sep)
        if depth > 3:
            dirs[:] = []
            continue

        dirs[:] = [
            d
            for d in dirs
            if d
            not in ["target", "build", ".gradle", "__pycache__", ".git", "node_modules"]
        ]

        if "requirements.txt" in files:
            return (
                "python",
                os.path.join(root, "requirements.txt"),
                "requirements.txt",
            )
        if "pom.xml" in files:
            return ("maven", os.path.join(root, "pom.xml"), "pom.xml")
        for gradle_file in ["build.gradle", "build.gradle.kts"]:
            if gradle_file in files:
                return ("gradle", os.path.join(root, gradle_file), gradle_file)
        if "build.sbt" in files:
            return ("sbt", os.path.join(root, "build.sbt"), "build.sbt")

    return ("unknown", "", "")


def collect_sbt_files(tmpdir: str) -> dict[str, str]:
    """Collect all SBT-related files for comprehensive dependency analysis"""
    sbt_files = {}

    for root, dirs, files in os.walk(tmpdir):
        depth = root[len(tmpdir) :].count(os.sep)
        if depth > 3:
            dirs[:] = []
            continue

        # Skip common build directories
        dirs[:] = [
            d
            for d in dirs
            if d
            not in ["target", "build", ".gradle", "__pycache__", ".git", "node_modules"]
        ]

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, tmpdir)

            # Collect main build.sbt files
            if (
                file == "build.sbt"
                or (file == "build.properties" and "project" in rel_path)
                or (file == "plugins.sbt" and "project" in rel_path)
            ):
                try:
                    with open(file_path, encoding="utf-8") as f:
                        sbt_files[rel_path] = f.read()
                except Exception as e:
                    print(f"Warning: Could not read {rel_path}: {e}")

    return sbt_files


def get_source_files(tmpdir: str, project_type: str) -> dict[str, str]:
    """Get source files for code analysis"""
    source_files = {}
    extensions = {
        "python": [".py"],
        "maven": [".java", ".scala"],
        "gradle": [".java", ".scala"],
        "sbt": [".scala", ".java"],
    }

    target_extensions = extensions.get(project_type, [])
    file_count = 0

    for root, dirs, files in os.walk(tmpdir):
        dirs[:] = [
            d
            for d in dirs
            if d not in ["target", "build", ".gradle", "__pycache__", ".git"]
        ]

        for file in files:
            if any(file.endswith(ext) for ext in target_extensions) and file_count < 10:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, tmpdir)
                try:
                    with open(full_path, encoding="utf-8") as f:
                        source_files[rel_path] = f.read()
                    file_count += 1
                except:
                    continue

    return source_files
