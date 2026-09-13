import json
import pathlib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def template():
    return yaml.safe_load((REPO / "backstage/template.yaml").read_text())


def test_is_a_scaffolder_template(template):
    assert template["kind"] == "Template"
    assert template["apiVersion"].startswith("scaffolder.backstage.io/")


def test_uses_the_cookiecutter_fetch_action(template):
    actions = [s["action"] for s in template["spec"]["steps"]]
    assert "fetch:cookiecutter" in actions
    assert "publish:github" in actions
    assert "catalog:register" in actions


# If these drift apart, the portal collects answers the template ignores.
def test_parameters_match_cookiecutter_variables(template):
    declared = set(json.loads((REPO / "template/cookiecutter.json").read_text()))
    exposed = set()
    for section in template["spec"]["parameters"]:
        exposed |= set(section.get("properties", {}))
    assert exposed == declared, f"missing {declared - exposed}, extra {exposed - declared}"
