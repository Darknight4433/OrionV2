# ORION V9: Tool Security Architecture & Permission Model

## 1. The Threat Model (Logic-Layer Risks)
Standard sandboxing protects the *Host OS*. It does not protect the *User's Life*.
We address four specific logic-layer threats:
1.  **Confused Deputy**: The LLM is tricked into using a legitimate tool (e.g., `send_email`) for a malicious purpose.
2.  **Parameter Tampering**: Valid tool, malicious payload (e.g., `google_search(query="how to build a bomb")`).
3.  **Resource Exhaustion**: The LLM loops a costly tool (e.g., `generate_image`) to drain API quotas ($$$).
4.  **Authorization Bypass**: The LLM accesses a tool meant only for the User (e.g., `delete_backup`).

## 2. The 5-Layer Defense Strategy

| Layer | Component | Function | Status |
| :--- | :--- | :--- | :--- |
| **L1** | **Intent Parser** | Converts Natural Language -> JSON. Discards garbage. | ✅ Implemented |
| **L2** | **Schema Validator** | Pydantic Checks. Enforces types, enums, and regex formats. | ✅ Implemented |
| **L3** | **Permission Matrix** | Static Policy. Checks `Role` vs `Tool.Level`. | 🚧 **Proposing** |
| **L4** | **Contextual Gate** | Dynamic Policy. Checks `RiskScore` vs `UserConfirmation`. | 🚧 **Proposing** |
| **L5** | **Execution Sandbox** | Runtime Isolation. Limits Network/FS access per tool. | 🚧 **Proposing** |

## 3. The Permission Matrix (Static Policy)

Every tool in ORION receives a classification profile.

### Risk Levels
*   **Safe (L0)**: Read-only, no side effects. (e.g., `get_time`, `weather`)
*   **Mundane (L1)**: Low impact, reversible. (e.g., `add_todo`, `play_music`)
*   **Sensitive (L2)**: Personal data access, financial cost. (e.g., `read_email`, `generate_image`)
*   **Critical (L3)**: Destructive, identity actions. (e.g., `delete_files`, `send_email`, `change_config`)

### Authorization Schema
| Tool | Risk Level | Auto-Run? | Rate Limit | Requires Auth? |
| :--- | :--- | :--- | :--- | :--- |
| `get_time` | Safe | ✅ Yes | 60/min | No |
| `add_task` | Mundane | ✅ Yes | 10/min | No |
| `send_email` | Critical | ❌ **Approval Required** | 5/hour | ✅ Identity Token |
| `delete_memory`| Critical | ❌ **Approval Required** | 1/day | ✅ Sudo Password |
| `google_search`| Sensitive | ✅ Yes (w/ Filter) | 20/min | No |

## 4. The Contextual Gate (Dynamic Policy)

Even if a tool is allowed, the *parameters* might be risky.

### Feature: Intent Risk Scoring
Before execution, the `ToolGatekeeper` analyzes params:
*   **Keywords**: Detects sensitive terms (`password`, `secret`, `key`, `bank`).
*   **Anomaly**: Detects unusual volume or targeting (e.g., `delete_task` x 50).
*   **Heuristics**:
    *   `if tool == 'google_search' and 'exploit' in query -> BLOCK`
    *   `if tool == 'send_email' and not recipient.in(contacts) -> WARN`

## 5. Implementation Strategy (The Gatekeeper Class)
The `ToolGatekeeper` wraps the execution logic.
```python
def execute_tool(intent, user_context):
    # 1. Static Check
    check_permission_matrix(intent.tool, user_context.role)
    
    # 2. Rate Limit Check
    check_rate_limit(intent.tool)
    
    # 3. Dynamic Scan
    risk_score = scan_parameters(intent.params)
    
    # 4. Critical Gate
    if tools[intent.tool].risk > Mundane or risk_score > Threshold:
        if not user_context.has_approved_explicitly:
            return RequestUserConfirmation(intent)

    # 5. Execute
    return actual_function(intent.params)
```

## 6. Audit Logging (Immutable)
All sensitive tool executions are logged to `data/audit_log.jsonl` (Append Only).
*   **Format**: `[ISO-TIMESTAMP] [UUID] [TOOL] [PARAMS] [USER_ID] [RISK_SCORE] [RESULT]`
*   **Security**: This file is hash-chained to detect deletion attempts.
