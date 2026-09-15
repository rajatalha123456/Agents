"""NFR-3: internal, authorized users only; role-based access to confidential docs.

This is a stub so the API shape is correct from day one. Replace `get_current_user`
with real auth (SSO/LDAP/JWT — you already have LDAP integration experience from
the EMS/GRC work) before this goes anywhere near production.
"""
from dataclasses import dataclass
from enum import Enum

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials


class Role(str, Enum):
    SHARIAH_OFFICER = "shariah_officer"
    SHARIAH_RESEARCHER = "shariah_researcher"
    SHARIAH_REVIEWER = "shariah_reviewer"  # only role allowed to approve/reject (FR-18)
    PRODUCT = "product"
    COMPLIANCE = "compliance"
    AUDITOR = "auditor"


@dataclass
class CurrentUser:
    user_id: str
    role: Role


basic_auth = HTTPBasic()


def get_current_user(
    credentials: HTTPBasicCredentials = Depends(basic_auth),
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_user_role: str = Header("shariah_researcher", alias="X-User-Role"),
) -> CurrentUser:
    if credentials.username != "admin" or credentials.password != "admin":
        raise HTTPException(status_code=401, detail="Invalid username or password")

    try:
        role = Role(x_user_role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown role: {x_user_role}")
    return CurrentUser(user_id=x_user_id, role=role)

def require_reviewer(user: CurrentUser) -> None:
    if user.role != Role.SHARIAH_REVIEWER:
        raise HTTPException(status_code=403, detail="Only a Shariah reviewer can approve/reject evidence packs.")
