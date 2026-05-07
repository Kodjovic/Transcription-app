"""
auth_routes.py — Endpoints d'authentification et d'administration.
"""

import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Response, Cookie, Depends
from pydantic import BaseModel, Field
from fastapi import Request
from fastapi.responses import Response

# Cookie sécurisé en production (HTTPS).
# Mettre COOKIE_SECURE=true dans .env quand déployé derrière HTTPS.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in ("true", "1", "yes")
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")

from auth import (
    SESSION_COOKIE,
    SESSION_DURATION,
    DEFAULT_CREDITS,
    COST_SIMPLE,
    COST_DIARIZE,
    ADMIN_CONTACT,
    get_user_by_code,
    create_session,
    delete_session,
    require_user,
    require_admin,
    list_users,
    create_user,
    add_credits,
    delete_user,
    user_public,
)


router = APIRouter()


# ─── Modèles ──────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=32)


class CreateUserRequest(BaseModel):
    name: Optional[str] = None
    credits: int = DEFAULT_CREDITS


class AddCreditsRequest(BaseModel):
    credits: int = Field(..., ge=-10000, le=10000)


# ─── Public config ────────────────────────────────────────────────────────────

@router.get("/config")
async def get_public_config():
    """Configuration publique (utilisée par le frontend)."""
    return {
        "default_credits": DEFAULT_CREDITS,
        "cost_simple":     COST_SIMPLE,
        "cost_diarize":    COST_DIARIZE,
        "admin_contact":   ADMIN_CONTACT,
    }
#--------------------------login--------------------
@router.options("/auth/login")
async def options_auth_login():
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )

# ─── Auth ─────────────────────────────────────────────────────────────────────

@router.post("/auth/login")
async def login(req: LoginRequest, response: Response):
    user = get_user_by_code(req.code)
    if not user:
        raise HTTPException(status_code=401, detail="Code d'accès invalide")

    return user_public(user)
    response.set_cookie(
    key=SESSION_COOKIE,
    value=token,
    max_age=SESSION_DURATION,
    httponly=True,
    samesite=COOKIE_SAMESITE,
    secure=COOKIE_SECURE,
)


@router.post("/auth/logout")
async def logout(
    response: Response,
    transcription_session: Optional[str] = Cookie(default=None),
):
    if transcription_session:
        delete_session(transcription_session)
    response.delete_cookie(SESSION_COOKIE)
    return {"success": True}


@router.get("/auth/me")
async def me(user: dict = Depends(require_user)):
    return user_public(user)


# ─── Admin ────────────────────────────────────────────────────────────────────

@router.get("/admin/users")
async def admin_list_users(_: dict = Depends(require_admin)):
    return [user_public(u, include_code=True) for u in list_users()]


@router.post("/admin/users")
async def admin_create_user(
    req: CreateUserRequest,
    _: dict = Depends(require_admin),
):
    user = create_user(name=req.name, credits=req.credits)
    return user_public(user, include_code=True)


@router.post("/admin/users/{user_id}/credits")
async def admin_add_credits(
    user_id: int,
    req: AddCreditsRequest,
    _: dict = Depends(require_admin),
):
    user = add_credits(user_id, req.credits)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return user_public(user, include_code=True)


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    _: dict = Depends(require_admin),
):
    ok = delete_user(user_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Impossible de supprimer cet utilisateur (admin ou inexistant)",
        )
    return {"success": True}
