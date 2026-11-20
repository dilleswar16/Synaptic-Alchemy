"""keigan/services/alert_source_service.py: webhook credential checks (token or HMAC signature)."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from keigan.entities.alert_entities import AlertSource
from keigan.services.alert_source_service import AlertSourceService, hash_secret

BODY = b'{"ruleId": "checkout-error-rate", "status": "firing"}'
CURRENT_SECRET = "kgn_current-secret-value"
PREVIOUS_SECRET = "kgn_previous-secret-value"


def _source(*, previous_secret: str | None = None, previous_valid_for: timedelta = timedelta(hours=1)) -> AlertSource:
    return AlertSource(
        webhook_secret_hash=hash_secret(CURRENT_SECRET),
        previous_webhook_secret_hash=hash_secret(previous_secret) if previous_secret else None,
        previous_secret_valid_until=datetime.now(UTC) + previous_valid_for if previous_secret else None,
    )


def _signature(key: str) -> str:
    return hmac.new(key.encode("utf-8"), BODY, hashlib.sha256).hexdigest()


def test_current_token_is_accepted() -> None:
    assert AlertSourceService._credentials_are_valid(_source(), BODY, CURRENT_SECRET, None) is True


def test_previous_token_is_accepted_during_rotation() -> None:
    assert AlertSourceService._credentials_are_valid(_source(previous_secret=PREVIOUS_SECRET), BODY, PREVIOUS_SECRET, None) is True


def test_previous_token_is_rejected_after_rotation_ends() -> None:
    source = _source(previous_secret=PREVIOUS_SECRET, previous_valid_for=timedelta(hours=-1))
    assert AlertSourceService._credentials_are_valid(source, BODY, PREVIOUS_SECRET, None) is False


def test_wrong_token_is_rejected() -> None:
    assert AlertSourceService._credentials_are_valid(_source(), BODY, "kgn_guess", None) is False


def test_missing_credentials_are_rejected() -> None:
    assert AlertSourceService._credentials_are_valid(_source(), BODY, None, None) is False


def test_signature_with_the_documented_key_is_accepted() -> None:
    # Documented contract: the HMAC-SHA256 key is the SHA-256 hex digest of the webhook secret.
    assert AlertSourceService._credentials_are_valid(_source(), BODY, None, "sha256=" + _signature(hash_secret(CURRENT_SECRET))) is True


def test_signature_forged_with_an_all_zero_key_is_rejected() -> None:
    # V1 (critical): without a rotation in progress the placeholder "previous" key must never verify a signature.
    assert AlertSourceService._credentials_are_valid(_source(), BODY, None, _signature("0" * 64)) is False


def test_signature_forged_with_an_all_zero_key_is_rejected_for_an_unknown_source() -> None:
    assert AlertSourceService._credentials_are_valid(None, BODY, None, _signature("0" * 64)) is False
