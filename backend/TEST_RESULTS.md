# Backend Test Report

## Run Summary

- Project: `nexus-sdlc/backend`
- Test framework: `pytest`
- Python: `3.12` via project virtual environment
- Executed on: `2026-03-21`
- Command:

```powershell
cd "C:\Users\sures\Downloads\nexus-sdlc-genai-architect (1)\nexus-sdlc\backend"
& "..\.venv\Scripts\python.exe" -m pytest -q
```

## Result

- Total test cases: `23`
- Passed: `23`
- Failed: `0`
- Final status: `PASS`

Latest verified output:

```text
.......................
23 passed, 30 warnings in 207.06s (0:03:27)
```

## Test Cases

### tests/test_main.py

1. `test_health_endpoint` - Passed
2. `test_agent_status_endpoint` - Passed
3. `test_request_detail_exposes_pipeline_status` - Passed

### tests/test_nexus.py

1. `test_register_success` - Passed
2. `test_register_duplicate` - Passed
3. `test_register_weak_password` - Passed
4. `test_login_success` - Passed
5. `test_login_wrong_password` - Passed
6. `test_me_authenticated` - Passed
7. `test_me_unauthenticated` - Passed
8. `test_refresh_token` - Passed
9. `test_create_request` - Passed
10. `test_create_request_validation_fail` - Passed
11. `test_get_request` - Passed
12. `test_list_requests` - Passed
13. `test_workflow_review_approve` - Passed
14. `test_approved_request_immutable` - Passed
15. `test_code_quality_clean` - Passed
16. `test_code_quality_detects_hardcoded_creds` - Passed
17. `test_security_headers_present` - Passed
18. `test_no_scope_access_denied` - Passed
19. `test_health_no_auth` - Passed
20. `test_protected_endpoint_no_token` - Passed

## What Is Covered

- Auth: register, login, refresh token, authenticated profile access
- Requests: create, list, fetch, validation, workflow state changes, immutability checks
- Agents: status endpoint and code-quality execution
- Security: protected route access and response headers
- UI-facing backend contract: request detail exposes `pipeline_status`

## Notes

- The suite currently completes successfully with warnings.
- The main warnings are from third-party packages and one SQLAlchemy relationship warning in the app code.
- Warnings do not block the current test run, but they are good cleanup candidates for a later pass.

## Useful Commands

Run all tests:

```powershell
& "..\.venv\Scripts\python.exe" -m pytest -q
```

Run with verbose output:

```powershell
& "..\.venv\Scripts\python.exe" -m pytest -vv
```

Run one file:

```powershell
& "..\.venv\Scripts\python.exe" -m pytest tests/test_nexus.py -vv
```

Run one test case:

```powershell
& "..\.venv\Scripts\python.exe" -m pytest tests/test_main.py::test_agent_status_endpoint -vv
```
