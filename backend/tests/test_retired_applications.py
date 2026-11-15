"""Retired application generation must not remain available to agents."""

import sys
from pathlib import Path


def test_application_tools_and_skills_are_not_exposed():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root.parent / "Oath"))
    from bootstrap.common.extension_loader import load_extensions

    extensions = load_extensions([root / "extensions"], kinds=frozenset({"tools", "skills"}))
    names = {tool.definition.name for tool in extensions.tools}
    assert not names & {"kit_build", "kit_call", "kit_dev", "tasks"}
    assert not (root / "services/kit-host").exists()
    assert not (root / "apps/ios/Hymio/Views/KitsScreen.swift").exists()
