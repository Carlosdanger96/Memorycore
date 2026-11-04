import pytest

from memorycore.service_lease import _lease_path, central_service_lease


def test_central_service_has_one_owner_and_releases_after_exit(tmp_path):
    target = tmp_path / "shared.db"
    with central_service_lease(target):
        with pytest.raises(RuntimeError, match="already owns"):
            with central_service_lease(target):
                pass
    with central_service_lease(target):
        pass


def test_postgres_lease_identity_excludes_credentials():
    first = "postgresql://writer:secret-a@127.0.0.1:5432/memorycore"
    second = "postgresql://reviewer:secret-b@127.0.0.1/memorycore"
    assert _lease_path(first) == _lease_path(second)
    assert _lease_path(first) == _lease_path(
        "postgresql+psycopg://reviewer:secret-c@127.0.0.1/memorycore"
    )
    assert "secret" not in str(_lease_path(first))
