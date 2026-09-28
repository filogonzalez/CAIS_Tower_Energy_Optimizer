from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml  # type: ignore[import-untyped]
from app.db import ALL_REGIONS, user_context_from_headers
from databricks.sdk.errors import NotFound, PermissionDenied, ResourceAlreadyExists
from databricks.sdk.service.database import DatabaseInstance
from lakebase.setup_lakebase import ensure_instance
from mock_data.config import REGIONS


class FakeDatabaseAPI:
    def __init__(self, get_error=None, create_error=None, create_result=None):
        self.get_error = get_error
        self.create_error = create_error
        self.create_result = create_result
        self.created: list[DatabaseInstance] = []

    def get_database_instance(self, name):
        if self.get_error:
            raise self.get_error
        return DatabaseInstance(name=name)

    def create_database_instance(self, database_instance):
        if self.create_error:
            raise self.create_error
        self.created.append(database_instance)
        return self.create_result


def _client(api):
    return SimpleNamespace(database=api)


def test_ensure_instance_creates_with_sdk_database_instance_object():
    api = FakeDatabaseAPI(get_error=NotFound("missing"))
    ensure_instance("teo-lakebase-dev", client=_client(api))
    assert len(api.created) == 1
    assert isinstance(api.created[0], DatabaseInstance)
    assert api.created[0].name == "teo-lakebase-dev"
    assert api.created[0].capacity == "CU_1"


def test_ensure_instance_waits_on_long_running_operation():
    waited = []
    waiter = SimpleNamespace(result=lambda: waited.append(True))
    api = FakeDatabaseAPI(get_error=NotFound("missing"), create_result=waiter)
    ensure_instance("teo", client=_client(api))
    assert waited == [True]


def test_ensure_instance_is_idempotent_when_instance_exists():
    api = FakeDatabaseAPI()
    ensure_instance("teo", client=_client(api))
    assert api.created == []


def test_ensure_instance_tolerates_concurrent_creation():
    api = FakeDatabaseAPI(get_error=NotFound("missing"), create_error=ResourceAlreadyExists("exists"))
    ensure_instance("teo", client=_client(api))


def test_ensure_instance_does_not_mask_permission_errors_with_create():
    api = FakeDatabaseAPI(get_error=PermissionDenied("denied"))
    with pytest.raises(PermissionDenied):
        ensure_instance("teo", client=_client(api))
    assert api.created == []


def test_all_regions_matches_canonical_regions():
    assert ALL_REGIONS == frozenset(REGIONS)


def test_user_without_region_header_sees_all_regions():
    user = user_context_from_headers({"X-Forwarded-Email": "a@example.com"})
    assert user.regions == ALL_REGIONS
    assert not user.can_approve


def test_region_header_restricts_scope():
    user = user_context_from_headers({"X-Forwarded-Email": "a@example.com", "X-TEO-Regions": "Metro,South"})
    assert user.regions == frozenset({"Metro", "South"})


def test_unauthenticated_request_is_rejected():
    with pytest.raises(PermissionError):
        user_context_from_headers({"X-TEO-Regions": "Metro"})


def test_app_value_from_keys_are_bound_as_app_resources():
    app_yaml = yaml.safe_load(Path("src/app/app.yaml").read_text(encoding="utf-8"))
    bundle = yaml.safe_load(Path("resources/app.yml").read_text(encoding="utf-8"))
    bound = {r["name"] for r in bundle["resources"]["apps"]["noc_app"]["resources"]}
    referenced = {e["valueFrom"] for e in app_yaml["env"] if "valueFrom" in e}
    assert referenced == {"database", "sql-warehouse", "serving-endpoint"}
    assert referenced <= bound


def test_app_requirements_match_project_sdk_pin():
    reqs = Path("src/app/requirements.txt").read_text(encoding="utf-8").split()
    assert "databricks-sdk>=0.60,<0.70" in reqs


def test_all_bundle_targets_use_existing_catalog():
    bundle = yaml.safe_load(Path("databricks.yml").read_text(encoding="utf-8"))
    assert bundle["variables"]["catalog"]["default"] == "tower_energy_optimizer"
    assert {target["variables"]["catalog"] for target in bundle["targets"].values()} == {
        "tower_energy_optimizer"
    }


def test_artifact_build_does_not_invoke_python_m_build():
    """The build command must not use ``python -m build`` because the
    deployment environment's system Python lacks the ``build`` package and
    pip.  Instead it delegates to a script that invokes the PEP 517 backend
    (setuptools.build_meta) directly."""
    bundle = yaml.safe_load(Path("databricks.yml").read_text(encoding="utf-8"))
    build_cmd = bundle["artifacts"]["default"]["build"]
    assert "python -m build" not in build_cmd
    assert "build_wheel.sh" in build_cmd


def test_build_wheel_script_invokes_pep517_backend():
    script = Path("scripts/build_wheel.sh")
    assert script.exists(), "build_wheel.sh must exist in scripts/"
    content = script.read_text(encoding="utf-8")
    assert "setuptools.build_meta" in content
    assert "build_wheel" in content
    assert "python -m build" not in content
