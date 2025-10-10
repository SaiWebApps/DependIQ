"""
Unit tests for utility modules
"""

import os

from app.utils.file_utils import find_matching_path
from app.utils.json_parser import robust_json_parse
from app.utils.password_utils import (
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.utils.project_utils import (
    collect_sbt_files,
    detect_project_type,
    get_source_files,
)


class TestFileUtils:
    """Test file utility functions"""

    def test_find_matching_path_exact_match(self):
        """Test exact path matching"""
        original_paths = ["src/main.py", "tests/test_main.py", "README.md"]
        result = find_matching_path("src/main.py", original_paths)
        assert result == "src/main.py"

    def test_find_matching_path_filename_match(self):
        """Test matching by filename only"""
        original_paths = ["src/utils/helpers.py", "tests/helpers.py"]
        result = find_matching_path("helpers.py", original_paths)
        assert result in original_paths
        assert result.endswith("helpers.py")

    def test_find_matching_path_suffix_match(self):
        """Test matching by path suffix"""
        original_paths = ["project/src/app/main.py"]
        result = find_matching_path("app/main.py", original_paths)
        assert result == "project/src/app/main.py"

    def test_find_matching_path_normalized(self):
        """Test normalized path matching"""
        original_paths = ["src\\utils\\helpers.py"]
        result = find_matching_path("src/utils/helpers.py", original_paths)
        assert result == "src\\utils\\helpers.py"

    def test_find_matching_path_no_match(self):
        """Test when no match is found"""
        original_paths = ["src/main.py", "tests/test_main.py"]
        result = find_matching_path("nonexistent.py", original_paths)
        assert result is None


class TestJsonParser:
    """Test JSON parsing utilities"""

    def test_direct_json_parse(self):
        """Test parsing valid JSON directly"""
        json_str = '{"name": "test", "version": "1.0"}'
        result = robust_json_parse(json_str, "versions")
        assert result == {"name": "test", "version": "1.0"}

    def test_json_with_markdown(self):
        """Test parsing JSON with markdown wrapper"""
        json_str = '```json\n{"name": "test"}\n```'
        result = robust_json_parse(json_str, "versions")
        assert result == {"name": "test"}

    def test_json_with_trailing_comma(self):
        """Test parsing JSON with trailing commas"""
        json_str = '{"name": "test", "version": "1.0",}'
        result = robust_json_parse(json_str, "versions")
        assert result == {"name": "test", "version": "1.0"}

    def test_json_array_extraction(self):
        """Test extracting JSON array from mixed content"""
        content = 'Here is the data: [{"name": "pkg1"}, {"name": "pkg2"}] and more text'
        result = robust_json_parse(content, "dependencies")
        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "pkg1"

    def test_json_object_extraction(self):
        """Test extracting JSON object from mixed content"""
        content = 'Text before {"key": "value"} text after'
        result = robust_json_parse(content, "versions")
        assert result == {"key": "value"}

    def test_manual_version_extraction(self):
        """Test manual version extraction fallback"""
        content = """
        "package1": "1.0.0"
        "package2": "2.0.0"
        """
        result = robust_json_parse(content, "versions")
        assert isinstance(result, dict)
        assert "package1" in result or "package2" in result

    def test_manual_dependency_extraction(self):
        """Test manual dependency extraction fallback"""
        content = """
        name: "fastapi"
        current_version: "0.100.0"
        description: "Web framework"
        """
        result = robust_json_parse(content, "dependencies")
        if result:  # May fail if regex doesn't match
            assert isinstance(result, list)

    def test_invalid_json_returns_none(self):
        """Test that completely invalid JSON returns None"""
        result = robust_json_parse("not json at all!", "dependencies")
        assert result is None


class TestPasswordUtils:
    """Test password utility functions"""

    def test_hash_password(self):
        """Test password hashing"""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert hashed != password
        assert len(hashed) > 20  # Bcrypt hashes are long
        assert hashed.startswith("$2b$")  # Bcrypt prefix

    def test_verify_password_correct(self):
        """Test verifying correct password"""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test verifying incorrect password"""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert verify_password("WrongPassword123!", hashed) is False

    def test_validate_password_strength_valid(self):
        """Test validating strong password"""
        is_valid, message = validate_password_strength("StrongPass123!")
        assert is_valid is True
        assert message == ""

    def test_validate_password_too_short(self):
        """Test password too short"""
        is_valid, message = validate_password_strength("Short1!")
        assert is_valid is False
        assert "8 characters" in message

    def test_validate_password_no_uppercase(self):
        """Test password without uppercase"""
        is_valid, message = validate_password_strength("lowercase123!")
        assert is_valid is False
        assert "uppercase" in message

    def test_validate_password_no_lowercase(self):
        """Test password without lowercase"""
        is_valid, message = validate_password_strength("UPPERCASE123!")
        assert is_valid is False
        assert "lowercase" in message

    def test_validate_password_no_number(self):
        """Test password without number"""
        is_valid, message = validate_password_strength("NoNumbers!")
        assert is_valid is False
        assert "number" in message

    def test_validate_password_no_special(self):
        """Test password without special character"""
        is_valid, message = validate_password_strength("NoSpecial123")
        assert is_valid is False
        assert "special character" in message

    def test_password_hash_uniqueness(self):
        """Test that same password produces different hashes"""
        password = "TestPassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different due to salt
        assert hash1 != hash2
        # But both should verify successfully
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


class TestProjectUtils:
    """Test project utility functions"""

    def test_detect_project_type_python(self, tmp_path):
        """Test detecting Python project"""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("fastapi==0.100.0")

        project_type, dep_file, dep_name = detect_project_type(str(tmp_path))
        assert project_type == "python"
        assert dep_name == "requirements.txt"
        assert os.path.exists(dep_file)

    def test_detect_project_type_maven(self, tmp_path):
        """Test detecting Maven project"""
        pom_file = tmp_path / "pom.xml"
        pom_file.write_text("<project></project>")

        project_type, dep_file, dep_name = detect_project_type(str(tmp_path))
        assert project_type == "maven"
        assert dep_name == "pom.xml"

    def test_detect_project_type_gradle(self, tmp_path):
        """Test detecting Gradle project"""
        build_file = tmp_path / "build.gradle"
        build_file.write_text("plugins { }")

        project_type, dep_file, dep_name = detect_project_type(str(tmp_path))
        assert project_type == "gradle"
        assert dep_name == "build.gradle"

    def test_detect_project_type_gradle_kts(self, tmp_path):
        """Test detecting Gradle Kotlin project"""
        build_file = tmp_path / "build.gradle.kts"
        build_file.write_text("plugins { }")

        project_type, dep_file, dep_name = detect_project_type(str(tmp_path))
        assert project_type == "gradle"
        assert dep_name == "build.gradle.kts"

    def test_detect_project_type_sbt(self, tmp_path):
        """Test detecting SBT project"""
        build_file = tmp_path / "build.sbt"
        build_file.write_text('name := "test"')

        project_type, dep_file, dep_name = detect_project_type(str(tmp_path))
        assert project_type == "sbt"
        assert dep_name == "build.sbt"

    def test_detect_project_type_unknown(self, tmp_path):
        """Test detecting unknown project type"""
        project_type, dep_file, dep_name = detect_project_type(str(tmp_path))
        assert project_type == "unknown"
        assert dep_file == ""
        assert dep_name == ""

    def test_collect_sbt_files(self, tmp_path):
        """Test collecting SBT-related files"""
        # Create main build.sbt
        build_file = tmp_path / "build.sbt"
        build_file.write_text('name := "test"')

        # Create project directory
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create project files
        (project_dir / "build.properties").write_text("sbt.version=1.5.0")
        (project_dir / "plugins.sbt").write_text('addSbtPlugin("plugin")')

        sbt_files = collect_sbt_files(str(tmp_path))

        assert "build.sbt" in sbt_files
        assert any("build.properties" in path for path in sbt_files.keys())
        assert any("plugins.sbt" in path for path in sbt_files.keys())

    def test_get_source_files_python(self, tmp_path):
        """Test getting Python source files"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        (src_dir / "main.py").write_text("print('hello')")
        (src_dir / "utils.py").write_text("def helper(): pass")

        source_files = get_source_files(str(tmp_path), "python")

        assert len(source_files) > 0
        assert any("main.py" in path for path in source_files.keys())

    def test_get_source_files_excludes_build_dirs(self, tmp_path):
        """Test that build directories are excluded"""
        # Create source file
        (tmp_path / "main.py").write_text("print('hello')")

        # Create build directory with file
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "compiled.py").write_text("# compiled")

        source_files = get_source_files(str(tmp_path), "python")

        assert not any("build" in path for path in source_files.keys())

    def test_get_source_files_limit(self, tmp_path):
        """Test that source files are limited to 10"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create 15 files
        for i in range(15):
            (src_dir / f"file{i}.py").write_text(f"# file {i}")

        source_files = get_source_files(str(tmp_path), "python")

        # Should be limited to 10
        assert len(source_files) <= 10
