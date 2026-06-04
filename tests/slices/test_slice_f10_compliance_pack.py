import pytest
from corvin.strategy.compliance_pack import CompliancePackBuilder, _sha256

def test_compliance_pack_builder_defaults():
    """Verify default configurations for the CompliancePackBuilder."""
    builder = CompliancePackBuilder()
    
    # Access private attributes for testing only
    assert builder._watermark == "CONFIDENTIAL — FOR AUDIT USE"
    assert builder._frameworks == ["SOX", "SOC2", "ISO27001"]
    assert builder._include_raw_evidence is True

def test_compliance_pack_builder_overrides():
    """Verify overrides via config dict."""
    config = {
        "watermark_text": "INTERNAL ONLY",
        "supported_frameworks": ["HIPAA"],
        "include_raw_evidence": False,
    }
    builder = CompliancePackBuilder(config=config)
    assert builder._watermark == "INTERNAL ONLY"
    assert builder._frameworks == ["HIPAA"]
    assert builder._include_raw_evidence is False

def test_sha256_helper():
    """Verify the SHA-256 helper works correctly."""
    data = b"test data"
    # echo -n "test data" | sha256sum -> 916f0027a575074ce72a331777c3478d6513f786a591bd892da1a577bf2335f9
    expected = "916f0027a575074ce72a331777c3478d6513f786a591bd892da1a577bf2335f9"
    assert _sha256(data) == expected
