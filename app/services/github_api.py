"""
GitHub API service for repository management and data fetching
"""

from datetime import datetime

import requests

from ..config import Config


class GitHubAPIService:
    """Service for interacting with GitHub API"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = Config.GITHUB_API_BASE
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "dependiq-App/1.0",
        }

    def get_user_repositories(
        self, per_page: int = 30, page: int = 1
    ) -> tuple[list[dict], bool]:
        """
        Fetch user's repositories with dependency file detection
        Returns tuple of (repositories, has_more_pages)
        """
        try:
            params = {
                "per_page": per_page,
                "page": page,
                "sort": "updated",
                "direction": "desc",
                "type": "all",  # Include both public and private repos
            }

            response = requests.get(
                f"{self.base_url}/user/repos",
                headers=self.headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()

            repositories = response.json()

            # Check if there are more pages
            link_header = response.headers.get("Link", "")
            has_more = 'rel="next"' in link_header

            # Process each repository to add dependency file information
            processed_repos = []
            for repo in repositories:
                processed_repo = self._process_repository_data(repo)
                processed_repos.append(processed_repo)

            return processed_repos, has_more

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch repositories: {e!s}")

    def _process_repository_data(self, repo: dict) -> dict:
        """Process raw repository data and add computed fields"""
        # Extract useful information
        processed = {
            "id": repo["id"],
            "name": repo["name"],
            "full_name": repo["full_name"],
            "description": repo.get("description", ""),
            "private": repo["private"],
            "language": repo.get("language"),
            "stargazers_count": repo["stargazers_count"],
            "forks_count": repo["forks_count"],
            "updated_at": repo["updated_at"],
            "default_branch": repo["default_branch"],
            "clone_url": repo["clone_url"],
            "html_url": repo["html_url"],
            "owner": {
                "login": repo["owner"]["login"],
                "avatar_url": repo["owner"]["avatar_url"],
            },
        }

        # Add formatted update time
        try:
            updated_dt = datetime.fromisoformat(
                repo["updated_at"].replace("Z", "+00:00")
            )
            now = datetime.now(updated_dt.tzinfo)
            diff = now - updated_dt

            if diff.days > 30:
                months = diff.days // 30
                processed["updated_display"] = f"{months}m ago"
            elif diff.days > 0:
                processed["updated_display"] = f"{diff.days}d ago"
            elif diff.seconds > 3600:
                hours = diff.seconds // 3600
                processed["updated_display"] = f"{hours}h ago"
            else:
                processed["updated_display"] = "Recently"
        except Exception:
            processed["updated_display"] = "Unknown"

        # Initialize dependency info (will be populated by separate calls if needed)
        processed["dependency_files"] = []
        processed["has_dependencies"] = False
        processed["project_type"] = "unknown"

        return processed

    def check_dependency_files(
        self, owner: str, repo: str, branch: str | None = None
    ) -> dict:
        """Check for dependency files in a repository"""
        if not branch:
            # Get default branch info first
            repo_info = self.get_repository_info(owner, repo)
            branch = repo_info.get("default_branch", "main")

        dependency_files = {
            "requirements.txt": "python",
            "pyproject.toml": "python",
            "pom.xml": "java",
            "build.gradle": "java",
            "build.gradle.kts": "java",
            "build.sbt": "scala",
            "package.json": "node",
            "Cargo.toml": "rust",
            "go.mod": "go",
        }

        found_files = []
        project_type = "unknown"

        for file_name, file_type in dependency_files.items():
            try:
                # Check if file exists in repository
                file_url = f"{self.base_url}/repos/{owner}/{repo}/contents/{file_name}"
                params = {"ref": branch}

                response = requests.get(
                    file_url, headers=self.headers, params=params, timeout=5
                )

                if response.status_code == 200:
                    file_data = response.json()
                    found_files.append(
                        {
                            "name": file_name,
                            "type": file_type,
                            "size": file_data.get("size", 0),
                            "path": file_data.get("path", file_name),
                        }
                    )

                    # Set project type based on first found dependency file
                    if project_type == "unknown":
                        project_type = file_type

            except Exception:
                # Ignore errors for individual file checks
                continue

        return {
            "dependency_files": found_files,
            "has_dependencies": len(found_files) > 0,
            "project_type": project_type,
        }

    def get_repository_info(self, owner: str, repo: str) -> dict:
        """Get detailed repository information"""
        try:
            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch repository info: {e!s}")

    def download_repository(self, owner: str, repo: str, ref: str = "main") -> bytes:
        """Download repository as ZIP archive"""
        try:
            # Use GitHub's archive download endpoint
            download_url = f"{self.base_url}/repos/{owner}/{repo}/zipball/{ref}"

            response = requests.get(
                download_url,
                headers=self.headers,
                timeout=30,  # Longer timeout for downloads
                stream=True,
            )
            response.raise_for_status()

            # Read the ZIP content
            zip_content = b""
            for chunk in response.iter_content(chunk_size=8192):
                zip_content += chunk

            return zip_content

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to download repository: {e!s}")

    def get_repository_branches(self, owner: str, repo: str) -> list[dict]:
        """Get list of branches for a repository"""
        try:
            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}/branches",
                headers=self.headers,
                params={"per_page": 10},  # Limit to most recent branches
                timeout=10,
            )
            response.raise_for_status()

            branches = response.json()
            return [
                {"name": branch["name"], "sha": branch["commit"]["sha"]}
                for branch in branches
            ]

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch branches: {e!s}")

    def get_repository_tags(self, owner: str, repo: str) -> list[dict]:
        """Get list of tags for a repository"""
        try:
            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}/tags",
                headers=self.headers,
                params={"per_page": 10},  # Limit to most recent tags
                timeout=10,
            )
            response.raise_for_status()

            tags = response.json()
            return [{"name": tag["name"], "sha": tag["commit"]["sha"]} for tag in tags]

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch tags: {e!s}")

    def search_repositories(self, query: str, per_page: int = 20) -> list[dict]:
        """Search user's repositories by name or description"""
        try:
            # Get user info first to get username
            user_response = requests.get(
                f"{self.base_url}/user", headers=self.headers, timeout=5
            )
            user_response.raise_for_status()
            username = user_response.json()["login"]

            # Search repositories with user scope
            search_query = f"{query} user:{username}"

            params = {"q": search_query, "per_page": per_page, "sort": "updated"}

            response = requests.get(
                f"{self.base_url}/search/repositories",
                headers=self.headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()

            search_results = response.json()
            return [
                self._process_repository_data(repo)
                for repo in search_results.get("items", [])
            ]

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to search repositories: {e!s}")
