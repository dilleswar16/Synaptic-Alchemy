"""keigan/integrations/secret_store.py: the local secret store never derives its key from a public default (V15)."""

from __future__ import annotations

import pytest

from keigan.config.settings import DEFAULT_LOCAL_TOKEN_SIGNING_SECRET, Settings
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.secret_store import LocalEncryptedSecretStore, create_secret_store


def settings_for(environment: str, encryption_key: str) -> Settings:
    """Bypass start-up validation on purpose: the store must refuse on its own as a second line of defence."""
    return Settings(_env_file=None).model_copy(
        update={
            "environment": environment,
            "secret_store_mode": "local_encrypted",
            "local_secret_encryption_key": encryption_key,
            "local_token_signing_secret": DEFAULT_LOCAL_TOKEN_SIGNING_SECRET,
        }
    )


@pytest.mark.parametrize("environment_name", ["dev", "prod"])
def test_local_store_refuses_to_borrow_the_signing_secret_as_key_outside_local_and_test(environment_name: str) -> None:
    with pytest.raises(IntegrationException, match="LOCAL_SECRET_ENCRYPTION_KEY"):
        create_secret_store(settings_for(environment_name, ""), credential_provider=None)  # type: ignore[arg-type]


def test_local_store_may_fall_back_to_the_signing_secret_on_a_developer_machine() -> None:
    assert isinstance(create_secret_store(settings_for("local", ""), credential_provider=None), LocalEncryptedSecretStore)  # type: ignore[arg-type]


def test_local_store_uses_the_configured_key_outside_local_and_test() -> None:
    assert isinstance(
        create_secret_store(settings_for("prod", "a-long-random-encryption-key-0123456789"), credential_provider=None),  # type: ignore[arg-type]
        LocalEncryptedSecretStore,
    )
