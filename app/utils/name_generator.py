"""
Random workspace name generator.

Produces adjective-noun pairs like "Swift Falcon" or "Quiet Harbor".
"""

import random

_ADJECTIVES = [
    "Swift",
    "Quiet",
    "Bold",
    "Bright",
    "Calm",
    "Keen",
    "Vivid",
    "Noble",
    "Rapid",
    "Sharp",
    "Sleek",
    "Steady",
    "Clear",
    "Grand",
    "Prime",
    "Iron",
    "Silver",
    "Golden",
    "Coral",
    "Amber",
]

_NOUNS = [
    "Falcon",
    "Harbor",
    "Circuit",
    "Summit",
    "Beacon",
    "Prism",
    "Atlas",
    "Forge",
    "Nexus",
    "Orbit",
    "Spark",
    "Vault",
    "Ridge",
    "Pulse",
    "Crest",
    "Flare",
    "Ember",
    "Drift",
    "Grove",
    "Haven",
]


def generate_workspace_name() -> str:
    """Generate a random adjective-noun workspace name."""
    adjective = random.choice(_ADJECTIVES)
    noun = random.choice(_NOUNS)
    return f"{adjective} {noun}"
