"""
payment_service.py — Intégration de l'API Chariow.

Référence : https://chariow.dev/llms.txt
Base URL  : https://api.chariow.com/v1

Le service expose une méthode `create_checkout` qui appelle l'endpoint
POST /v1/checkout de Chariow et renvoie un dict normalisé :

    {
      "step":         "payment" | "completed" | "already_purchased",
      "checkout_url": "...",     # quand step == "payment"
      "sale_id":      "sal_...", # quand step == "payment"
      "message":      "...",     # cas d'erreur ou already_purchased
    }

Les erreurs HTTP de Chariow (401/404/422/429) sont converties en
exceptions `PaymentError` avec un message utilisateur final.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


CHARIOW_BASE_URL = "https://api.chariow.com/v1"
TIMEOUT_SECONDS  = 15.0


class PaymentError(Exception):
    """Erreur métier de paiement (message à afficher à l'utilisateur)."""
    def __init__(self, message: str, status_code: int = 502, fields: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.fields = fields or {}


class ChariowService:
    def __init__(self) -> None:
        self.api_key                  = os.getenv("CHARIOW_API_KEY", "").strip()
        self.product_id_standard      = os.getenv("CHARIOW_PRODUCT_ID_STANDARD", "").strip()
        self.product_id_premium       = os.getenv("CHARIOW_PRODUCT_ID_PREMIUM", "").strip()
        self.payment_currency         = os.getenv("PAYMENT_CURRENCY", "XOF").strip().upper()
        self.public_base_url          = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        self.credits_standard         = int(os.getenv("CREDITS_STANDARD", "200"))
        self.credits_premium          = int(os.getenv("CREDITS_PREMIUM", "500"))

    # ─── Métadonnées des plans ─────────────────────────────────────────────

    def is_configured(self) -> bool:
        return bool(
            self.api_key
            and self.product_id_standard
            and self.product_id_premium
            and self.public_base_url
        )

    def get_plan(self, plan: str) -> Dict[str, Any]:
        plan = (plan or "").lower()
        if plan == "standard":
            return {
                "key":        "standard",
                "label":      "Standard",
                "product_id": self.product_id_standard,
                "credits":    self.credits_standard,
                "amount":     3000,
            }
        if plan == "premium":
            return {
                "key":        "premium",
                "label":      "Premium",
                "product_id": self.product_id_premium,
                "credits":    self.credits_premium,
                "amount":     5000,
            }
        raise PaymentError(f"Plan inconnu : {plan}", status_code=400)

    def credits_for_plan(self, plan: str) -> int:
        return self.get_plan(plan)["credits"]

    # ─── Création d'un checkout ────────────────────────────────────────────

    async def create_checkout(
        self,
        *,
        plan: str,
        purchase_ref: str,
        email: str,
        first_name: str,
        last_name: str,
        phone_number: str,
        phone_country_code: str,
    ) -> Dict[str, Any]:
        """
        Appelle POST /v1/checkout et retourne un dict normalisé (cf. doc en tête).
        """
        if not self.is_configured():
            raise PaymentError(
                "Le système de paiement n'est pas configuré sur le serveur. "
                "Contactez l'administrateur.",
                status_code=503,
            )

        plan_info = self.get_plan(plan)

        redirect_url = f"{self.public_base_url}/app/success.html?ref={purchase_ref}"

        payload = {
            "product_id":  plan_info["product_id"],
            "email":       email,
            "first_name":  first_name,
            "last_name":   last_name,
            "phone": {
                "number":       phone_number,
                "country_code": phone_country_code,
            },
            "payment_currency": self.payment_currency,
            "redirect_url":     redirect_url,
            "custom_metadata": {
                "purchase_ref": purchase_ref,
                "plan":         plan_info["key"],
                "source":       "transcription_pro_app",
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{CHARIOW_BASE_URL}/checkout",
                    headers=headers,
                    json=payload,
                )
        except httpx.RequestError as exc:
            logger.error(f"Chariow request error : {exc}")
            raise PaymentError(
                "Impossible de joindre le service de paiement. "
                "Vérifiez votre connexion et réessayez.",
                status_code=502,
            )

        # ─── Gestion des erreurs HTTP ────────────────────────────────────
        if resp.status_code >= 400:
            try:
                err_body = resp.json()
            except Exception:
                err_body = {}

            logger.warning(
                f"Chariow {resp.status_code} : {err_body.get('message', resp.text[:200])}"
            )

            if resp.status_code == 401:
                raise PaymentError(
                    "Erreur de configuration du système de paiement. "
                    "Contactez l'administrateur.",
                    status_code=500,
                )
            if resp.status_code == 404:
                raise PaymentError(
                    "Cette offre n'est pas disponible actuellement.",
                    status_code=404,
                )
            if resp.status_code == 422:
                raise PaymentError(
                    err_body.get("message") or "Les informations fournies sont invalides.",
                    status_code=422,
                    fields=err_body.get("errors") or {},
                )
            if resp.status_code == 429:
                raise PaymentError(
                    "Trop de tentatives. Veuillez réessayer dans un instant.",
                    status_code=429,
                )

            raise PaymentError(
                err_body.get("message") or "Service de paiement indisponible.",
                status_code=502,
            )

        try:
            data = resp.json().get("data", {})
        except Exception:
            raise PaymentError("Réponse invalide du service de paiement.", 502)

        step = data.get("step")

        if step == "payment":
            payment    = data.get("payment", {}) or {}
            purchase   = data.get("purchase", {}) or {}
            checkout_url = payment.get("checkout_url")
            sale_id      = purchase.get("id")
            if not checkout_url:
                raise PaymentError("URL de paiement absente de la réponse Chariow.", 502)
            return {
                "step":         "payment",
                "checkout_url": checkout_url,
                "sale_id":      sale_id,
            }

        if step == "completed":
            # Produit gratuit (ne devrait pas arriver dans notre cas) — on
            # considère que le paiement est immédiatement fulfilled.
            return {
                "step":    "completed",
                "sale_id": (data.get("purchase") or {}).get("id"),
            }

        if step == "already_purchased":
            return {
                "step":    "already_purchased",
                "message": data.get("message") or "Vous avez déjà acheté cette offre.",
            }

        # Step inconnu
        logger.error(f"Chariow step inconnu : {step}")
        raise PaymentError("Réponse inattendue du service de paiement.", 502)
