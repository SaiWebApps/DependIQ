"""
Robust JSON parsing with multiple fallback strategies
"""

import json
import re


def robust_json_parse(content: str, parse_type: str = "dependencies"):
    """Robust JSON parsing with multiple fallback strategies"""

    # Strategy 1: Direct parse
    try:
        result = json.loads(content)
        print("✅ Strategy 1 SUCCESS: Direct JSON parse")
        return result
    except json.JSONDecodeError as e:
        print(f"❌ Strategy 1 FAILED: {e}")

    # Strategy 2: Clean markdown and common issues (CAREFUL with regex)
    try:
        cleaned = content.strip()
        print(f"🔧 Strategy 2: Cleaning {len(cleaned)} chars")

        # Remove markdown formatting carefully
        if "```json" in cleaned:
            cleaned = cleaned.replace("```json", "")
        if "```" in cleaned:
            cleaned = cleaned.replace("```", "")
        cleaned = cleaned.strip()

        # Only fix trailing commas - don't touch keys!
        cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)

        result = json.loads(cleaned)
        print("✅ Strategy 2 SUCCESS: Markdown cleanup worked")
        return result
    except json.JSONDecodeError as e:
        print(f"❌ Strategy 2 FAILED: {e}")
        print(f"   Cleaned content preview: {cleaned[:200]}...")

    # Strategy 3: Extract JSON block from mixed content
    try:
        print("🔧 Strategy 3: Extracting JSON block")

        if parse_type == "dependencies":
            # Look for array
            match = re.search(r"\[.*\]", content, re.DOTALL)
        else:
            # Look for object
            match = re.search(r"\{.*\}", content, re.DOTALL)

        if match:
            json_str = match.group(0)
            print(f"   Found JSON block: {len(json_str)} chars")

            # Only fix trailing commas
            json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)

            result = json.loads(json_str)
            print("✅ Strategy 3 SUCCESS: JSON extraction worked")
            return result
        else:
            print("❌ Strategy 3: No JSON block found")
    except json.JSONDecodeError as e:
        print(f"❌ Strategy 3 FAILED: {e}")

    # Strategy 4: Manual key-value extraction for versions
    if parse_type == "versions":
        try:
            print("🔧 Strategy 4: Manual version extraction")

            # Extract "key": "value" pairs
            pattern = r'"([^"]+)":\s*"([^"]+)"'
            matches = re.findall(pattern, content)

            if matches:
                result = {key: value for key, value in matches}
                print(f"✅ Strategy 4 SUCCESS: Extracted {len(result)} version pairs")
                return result
            else:
                print("❌ Strategy 4: No key-value pairs found")
        except Exception as e:
            print(f"❌ Strategy 4 FAILED: {e}")

    # Strategy 5: Manual parsing for dependencies
    elif parse_type == "dependencies":
        try:
            print("🔧 Strategy 5: Manual dependency extraction")

            deps = []

            # Look for dependency objects
            name_pattern = r'"?name"?\s*:\s*"([^"]+)"'
            version_pattern = r'"?current_version"?\s*:\s*"([^"]+)"'
            desc_pattern = r'"?description"?\s*:\s*"([^"]+)"'

            names = re.findall(name_pattern, content)
            versions = re.findall(version_pattern, content)
            descriptions = re.findall(desc_pattern, content)

            for i, name in enumerate(names):
                version = versions[i] if i < len(versions) else "unknown"
                description = descriptions[i] if i < len(descriptions) else ""
                deps.append(
                    {
                        "name": name,
                        "current_version": version,
                        "description": description,
                    }
                )

            if deps:
                print(f"✅ Strategy 5 SUCCESS: Extracted {len(deps)} dependencies")
                return deps
            else:
                print("❌ Strategy 5: No dependencies found")
        except Exception as e:
            print(f"❌ Strategy 5 FAILED: {e}")

    print(f"❌ ALL JSON PARSING STRATEGIES FAILED for {parse_type}")
    print(f"Content length: {len(content)}")
    print(f"Full content: {content}")
    return None
