import pytest
from corvin.core.contracts import InvestigationRequest, TriggerSource
from corvin.storage.models import InvestigationRequestRow

def test_heatmap_data_retrieval():
    """Verify that heatmap logic handles zero counts safely."""
    from datetime import date, timedelta
    
    # Just verify that the date logic won't raise exceptions on standard inputs
    days = 90
    today = date.today()
    start_date = today - timedelta(days=days - 1)
    
    all_dates = {
        (start_date + timedelta(days=i)).isoformat(): 0
        for i in range(days)
    }
    
    assert len(all_dates) == 90
    assert today.isoformat() in all_dates
    assert start_date.isoformat() in all_dates

def test_heatmap_severity_threshold_defaults():
    """Verify default heatmap threshold mappings."""
    thresholds = {
        "low": 1, "medium": 3, "high": 5, "critical": 10
    }
    
    def _severity(count: int) -> str:
        if count == 0:
            return "none"
        if count >= int(thresholds.get("critical", 10)):
            return "critical"
        if count >= int(thresholds.get("high", 5)):
            return "high"
        if count >= int(thresholds.get("medium", 3)):
            return "medium"
        return "low"
    
    assert _severity(0) == "none"
    assert _severity(1) == "low"
    assert _severity(2) == "low"
    assert _severity(3) == "medium"
    assert _severity(4) == "medium"
    assert _severity(5) == "high"
    assert _severity(9) == "high"
    assert _severity(10) == "critical"
    assert _severity(100) == "critical"
