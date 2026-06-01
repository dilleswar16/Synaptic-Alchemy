# Predictive Penalty: MISSED

**Service:** fundapis  
**Date:** 2026-06-01T17:22:35Z  
**Investigation:** 0bd8c879-3ef4-4c60-afee-d58812c57fa4  

MISSED PATTERN for fundapis: The predictive engine failed to detect this failure mode.
Root Cause: Heap growth plus restart churn.
Contributing Factors: OOM risk, Error spike
What to watch for: Monitor for the combination of these signals before similar incidents. Consider adding a heuristic check for this pattern.

**Threshold Suggestion:** Add new heuristic rule for this failure mode or lower existing thresholds by 15-20%.
