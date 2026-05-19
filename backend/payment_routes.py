"""
payment_routes.py — Endpoints de paiement Chariow.

Routes
──────
POST   /payment/checkout              Crée une session de checkout Chariow
GET    /payment/purchase/{ref}        Récupère l'état d'un achat (polling page de succès)
POST   /webhooks/chariow/{secret}     Webhook (Pulse) — confirme un paiement et délivre le code

Sécurité
────────
- La clé API Chariow est lue depuis l'environnement, jamais exposée au client.
- L'URL du webhook contient un secret partagé (CHARIOW_WEBHOOK_SECRET) configuré
  dans le dashboard Chariow. Toute requête sans le bon secret est rejetée.
- Les webhooks sont idempotents : `fulfill_purchase` ne crée le code qu'une fois.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth import (
    create_purchase,
    fulfill_purchase,
    get_purchase_by_ref,
    mark_purchase_status,
    update_purchase_sale_id,
)
from payment_service import ChariowService, PaymentError

logger = logging.getLogger(__name__)

router = APIRouter()

_chariow = ChariowService()


# ─── Modèles ──────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan:               str = Field(..., pattern=r"^(standard|premium)$")
    email:              str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    first_name:         str = Field(..., min_length=1, max_length=50)
    last_name:          str = Field(..., min_length=1, max_length=50)
    phone_number:       str = Field(..., min_length=6, max_length=20)
    phone_country_code: str = Field("TG", min_length=2, max_length=2)


class CheckoutResponse(BaseModel):
    step:         str
    checkout_url: str | None = None
    purchase_ref: str | None = None
    message:      str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _new_purchase_ref() -> str:
    """Référence interne courte et URL-safe : ord_xxxxxxxxxxxx"""
    return f"ord_{secrets.token_urlsafe(9)}"


def _clean_phone(raw: str) -> str:
    """Retire tous les caractères non numériques (Chariow attend des chiffres uniquement)."""
    return re.sub(r"\D", "", raw or "")


def _public_purchase(purchase: dict) -> dict:
    """Vue publique d'un purchase (sans détails internes)."""
    return {
        "ref":             purchase["purchase_ref"],
        "status":          purchase["status"],
        "plan":            purchase["plan"],
        "amount":          purchase["amount"],
        "user_code":       purchase.get("user_code"),
        "credits_granted": purchase.get("credits_granted"),
        "customer_email":  purchase["customer_email"],
    }


# ─── POST /payment/checkout ───────────────────────────────────────────────────

@router.post("/payment/checkout", response_model=CheckoutResponse)
async def create_checkout(body: CheckoutRequest):
    """Crée une session de paiement Chariow et renvoie l'URL de checkout."""

    plan_info    = _chariow.get_plan(body.plan)
    purchase_ref = _new_purchase_ref()
    phone        = _clean_phone(body.phone_number)

    # 1) On crée le purchase EN BASE AVANT l'appel Chariow, pour pouvoir
    #    le retrouver dans le webhook même si l'utilisateur ferme l'onglet.
    create_purchase(
        purchase_ref   = purchase_ref,
        plan           = plan_info["key"],
        amount         = plan_info["amount"],
        customer_email = body.email,
        customer_name  = f"{body.first_name} {body.last_name}".strip(),
        customer_phone = phone,
    )

    # 2) Appel Chariow
    try:
        result = await _chariow.create_checkout(
            plan               = plan_info["key"],
            purchase_ref       = purchase_ref,
            email              = body.email,
            first_name         = body.first_name.strip(),
            last_name          = body.last_name.strip(),
            phone_number       = phone,
            phone_country_code = body.phone_country_code.upper(),
        )
    except PaymentError as err:
        logger.warning(f"Checkout refusé pour {purchase_ref} : {err.message}")
        # On laisse le purchase en 'pending' — pas de fulfillment fait.
        detail = {"message": err.message}
        if err.fields:
            detail["fields"] = err.fields
        raise HTTPException(status_code=err.status_code, detail=detail)

    # 3) Stocker le sale_id si Chariow nous l'a renvoyé
    if result.get("sale_id"):
        update_purchase_sale_id(purchase_ref, result["sale_id"])

    if result["step"] == "payment":
        return CheckoutResponse(
            step         = "payment",
            checkout_url = result["checkout_url"],
            purchase_ref = purchase_ref,
        )

    if result["step"] == "completed":
        # Produit gratuit — on délivre le code immédiatement
        user = fulfill_purchase(
            purchase_ref = purchase_ref,
            credits      = plan_info["credits"],
        )
        return CheckoutResponse(
            step         = "completed",
            purchase_ref = purchase_ref,
            message      = "Achat finalisé. Votre code est prêt." if user else None,
        )

    if result["step"] == "already_purchased":
        mark_purchase_status(purchase_ref, "abandoned",
                             webhook_payload="already_purchased")
        return CheckoutResponse(
            step    = "already_purchased",
            message = result.get("message"),
        )

    raise HTTPException(status_code=502, detail={"message": "Réponse inattendue."})


# ─── GET /payment/purchase/{ref} ──────────────────────────────────────────────

@router.get("/payment/purchase/{purchase_ref}")
async def get_purchase_status(purchase_ref: str):
    """Polling depuis la page success.html : renvoie l'état (et le code si paid)."""
    purchase = get_purchase_by_ref(purchase_ref)
    if not purchase:
        raise HTTPException(status_code=404, detail="Référence d'achat inconnue.")
    return _public_purchase(purchase)


# ─── POST /webhooks/chariow/{secret} ──────────────────────────────────────────

@router.post("/webhooks/chariow/{secret}")
async def chariow_webhook(secret: str, request: Request):
    """
    Reçoit les événements (Pulses) Chariow.

    URL à configurer dans Chariow Dashboard → Automation → Pulses :
        https://VOTRE_DOMAINE/webhooks/chariow/{CHARIOW_WEBHOOK_SECRET}

    Événements gérés :
      - successful.sale  → crée le code utilisateur (idempotent)
      - failed.sale      → marque le purchase 'failed'
      - abandoned.sale   → marque le purchase 'abandoned'
    """
    expected = (os.getenv("CHARIOW_WEBHOOK_SECRET") or "").strip()
    if not expected or not secrets.compare_digest(secret, expected):
        # On ne donne aucun indice d'erreur précis pour ne pas aider un attaquant
        logger.warning("Webhook Chariow : secret invalide")
        raise HTTPException(status_code=404, detail="Not found")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = (payload.get("event") or "").lower()
    sale  = payload.get("sale") or {}
    meta  = sale.get("custom_metadata") or payload.get("custom_metadata") or {}
    purchase_ref = meta.get("purchase_ref")

    logger.info(f"Webhook Chariow reçu : event={event} ref={purchase_ref}")

    if not purchase_ref:
        # Pas notre référence — on accuse réception sans rien faire pour ne pas
        # déclencher un retry.
        return {"ok": True, "ignored": "missing purchase_ref"}

    purchase = get_purchase_by_ref(purchase_ref)
    if not purchase:
        logger.warning(f"Webhook : purchase_ref inconnu en base : {purchase_ref}")
        return {"ok": True, "ignored": "unknown purchase_ref"}

    payload_json = json.dumps(payload)[:4000]  # tronqué pour la BDD

    if event == "successful.sale":
        plan    = purchase["plan"]
        credits = _chariow.credits_for_plan(plan)
        user = fulfill_purchase(
            purchase_ref    = purchase_ref,
            credits         = credits,
            webhook_payload = payload_json,
        )
        if not user:
            logger.error(f"fulfill_purchase a renvoyé None pour {purchase_ref}")
            raise HTTPException(status_code=500, detail="Fulfillment failed")
        return {"ok": True, "user_code": user["code"]}

    if event == "failed.sale":
        mark_purchase_status(purchase_ref, "failed", webhook_payload=payload_json)
        return {"ok": True}

    if event == "abandoned.sale":
        mark_purchase_status(purchase_ref, "abandoned", webhook_payload=payload_json)
        return {"ok": True}

    # Autres événements (license.*) — accusé de réception sans traitement
    return {"ok": True, "ignored": event}


# ─── Statut configuration (debug / health) ────────────────────────────────────

@router.get("/payment/config")
async def payment_config():
    """Retourne juste les infos publiques nécessaires au frontend."""
    return {
        "configured": _chariow.is_configured(),
        "currency":   _chariow.payment_currency,
        "plans": {
            "standard": {"amount": 3000, "credits": _chariow.credits_standard},
            "premium":  {"amount": 5000, "credits": _chariow.credits_premium},
        },
    }
