"""
File operation utilities
"""

import os


def find_matching_path(chatgpt_path: str, original_paths: list[str]) -> str | None:
    """Find the original file path that matches ChatGPT's returned path"""
    print(
        f"🔍 MATCHING: Looking for '{chatgpt_path}' in {len(original_paths)} original paths"
    )

    # Try exact match first
    if chatgpt_path in original_paths:
        print(f"✅ EXACT MATCH: {chatgpt_path}")
        return chatgpt_path

    # Try matching by filename only
    chatgpt_filename = os.path.basename(chatgpt_path)
    for original_path in original_paths:
        if os.path.basename(original_path) == chatgpt_filename:
            print(f"✅ FILENAME MATCH: '{chatgpt_path}' → '{original_path}'")
            return original_path

    # Try matching by suffix (ChatGPT path as suffix of original)
    for original_path in original_paths:
        if original_path.endswith(chatgpt_path):
            print(f"✅ SUFFIX MATCH: '{chatgpt_path}' → '{original_path}'")
            return original_path

    # Try matching if ChatGPT path contains the original filename and path parts
    for original_path in original_paths:
        if chatgpt_path in original_path or original_path.replace(
            "\\", "/"
        ) in chatgpt_path.replace("\\", "/"):
            print(f"✅ PARTIAL MATCH: '{chatgpt_path}' → '{original_path}'")
            return original_path

    # Try normalizing paths and matching
    chatgpt_normalized = chatgpt_path.replace("\\", "/").strip("/")
    for original_path in original_paths:
        original_normalized = original_path.replace("\\", "/").strip("/")

        # Check if normalized paths match at the end
        if original_normalized.endswith(
            chatgpt_normalized
        ) or chatgpt_normalized.endswith(original_normalized):
            print(f"✅ NORMALIZED MATCH: '{chatgpt_path}' → '{original_path}'")
            return original_path

    print(f"❌ NO MATCH FOUND for '{chatgpt_path}'")
    print(
        f"   Available original paths: {original_paths[:10]}..."
    )  # Show first 10 for debugging
    return None
