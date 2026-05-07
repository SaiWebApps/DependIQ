"""GitHub OAuth service — standalone functions for GitHub API access."""

from typing import Any

import httpx


async def get_github_repositories(access_token: str) -> list[dict[str, Any]]:
    """Fetch user's GitHub repositories. Used by app/api/projects.py."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    repos: list[dict[str, Any]] = []
    page = 1
    async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
        while True:
            resp = await client.get(
                f"https://api.github.com/user/repos?per_page=100&page={page}&sort=updated",
                headers=headers,
            )
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
            if len(batch) < 100:
                break
    return repos
