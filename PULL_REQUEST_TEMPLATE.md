# Add aim prediction and input latency optimizations

This PR adds an aim-prediction module and input-latency measurement/optimization helpers, with Windows 11 capture-card support and examples. Files added include:
- aim_prediction/latency.py
- aim_prediction/predictor.py
- examples/udp_capture_integration.py
- docs/latency.md
- docs/windows.md
- tools/*.py
- requirements.txt
- tests

Summary of changes and testing instructions are in the PR description and docs. Please run CI (pytest) and review Windows capture instructions in docs/windows.md.