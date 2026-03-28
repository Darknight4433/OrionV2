from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

# --- Security Primitives ---

class RiskLevel(str, Enum):
    SAFE = "safe"           # Read-only, no cost (e.g., time)
    MUNDANE = "mundane"     # Low impact, reversible (e.g., add to-do)
    SENSITIVE = "sensitive" # PII access, API costs (e.g., geo, gen-ai)
    CRITICAL = "critical"   # Destructive, external comms (e.g., email, delete)

class AuthRequirement(str, Enum):
    NONE = "none"
    USER_PRESENCE = "user_presence" # User is active/awake
    EXPLICIT_APPROVAL = "approval"  # "Do you want me to X?"
    SUDO = "sudo"                   # Password/Biometric required

# --- Tool Definitions ---

class ToolSecurityProfile(BaseModel):
    name: str
    risk_level: RiskLevel
    auth_requirement: AuthRequirement
    rate_limit_per_min: int
    parameter_blacklist: List[str] = Field(default_factory=list)
    
    class Config:
        frozen = True

# --- The Permission Matrix ---

class PermissionMatrix:
    # This would ideally load from a YAML/JSON config file
    _registry: Dict[str, ToolSecurityProfile] = {
        "get_time": ToolSecurityProfile(
            name="get_time",
            risk_level=RiskLevel.SAFE,
            auth_requirement=AuthRequirement.NONE,
            rate_limit_per_min=60
        ),
        "add_task": ToolSecurityProfile(
            name="add_task",
            risk_level=RiskLevel.MUNDANE,
            auth_requirement=AuthRequirement.NONE,
            rate_limit_per_min=10
        ),
        "google_search": ToolSecurityProfile(
            name="google_search",
            risk_level=RiskLevel.SENSITIVE,
            auth_requirement=AuthRequirement.NONE,
            rate_limit_per_min=20,
            parameter_blacklist=["exploit", "hack", "bypass", "bomb"]
        ),
        "send_notification": ToolSecurityProfile(
            name="send_notification",
            risk_level=RiskLevel.MUNDANE,
            auth_requirement=AuthRequirement.NONE,
            rate_limit_per_min=30
        ),
        "delete_memory": ToolSecurityProfile(
            name="delete_memory",
            risk_level=RiskLevel.CRITICAL,
            auth_requirement=AuthRequirement.EXPLICIT_APPROVAL,
            rate_limit_per_min=1
        ),
         "execute_code": ToolSecurityProfile(
            name="execute_code",
            risk_level=RiskLevel.CRITICAL,
            auth_requirement=AuthRequirement.SUDO,
            rate_limit_per_min=1
        )
    }

    @classmethod
    def get_profile(cls, tool_name: str) -> Optional[ToolSecurityProfile]:
        return cls._registry.get(tool_name)

    @classmethod
    def check_permissions(cls, tool_name: str, params: dict) -> Dict:
        """
        Returns {'allowed': bool, 'reason': str, 'needs_approval': bool}
        """
        profile = cls.get_profile(tool_name)
        if not profile:
            return {"allowed": False, "reason": "Tool not registered in security matrix", "needs_approval": False}

        # Check Blacklist in Params (Basic concept)
        for key, value in params.items():
            if isinstance(value, str):
                for bad_word in profile.parameter_blacklist:
                    if bad_word in value.lower():
                        return {"allowed": False, "reason": f"Parameter blocked by blacklist: {bad_word}", "needs_approval": False}

        # Check Auth Requirement
        if profile.auth_requirement in [AuthRequirement.EXPLICIT_APPROVAL, AuthRequirement.SUDO]:
             return {"allowed": True, "reason": "Requires Approval", "needs_approval": True}
             
        return {"allowed": True, "reason": "Authorized", "needs_approval": False}
