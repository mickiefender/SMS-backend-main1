import logging
import os

import requests

logger = logging.getLogger(__name__)


class ArkeselError(Exception):
    """A safe, user-facing provider error (never contains credentials)."""


class ArkeselProvider:
    """Small provider adapter. Credentials are read only on the server."""

    def __init__(self, api_key=None, base_url=None, timeout=15):
        self.api_key = api_key or os.environ.get("ARKESEL_API_KEY", "")
        self.base_url = (base_url or os.environ.get(
            "ARKESEL_BASE_URL", "https://sms.arkesel.com/api/v2"
        )).rstrip("/")
        self.timeout = timeout

    def send(self, sender_id, recipients, message):
        if not self.api_key:
            raise ArkeselError("SMS service is temporarily unavailable. Please try again.")
        if not recipients:
            raise ArkeselError("No valid recipients were supplied.")
        payload = {
            "sender": sender_id,
            "message": message,
            "recipients": recipients,
        }
        try:
            response = requests.post(
                f"{self.base_url}/sms/send",
                json=payload,
                headers={"api-key": self.api_key, "Content-Type": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as exc:
                raise ArkeselError("SMS service is temporarily unavailable. Please try again.") from exc
            if not isinstance(data, dict):
                raise ArkeselError("SMS service is temporarily unavailable. Please try again.")
            # Arkesel has used both code/status fields across API versions.
            code = str(data.get("code", data.get("status", ""))).lower()
            if code in {"401", "403", "400", "failed", "error"}:
                raise ArkeselError("SMS service is temporarily unavailable. Please try again.")
            return data
        except ArkeselError:
            raise
        except (requests.Timeout, requests.ConnectionError) as exc:
            logger.warning("Arkesel request failed: %s", exc.__class__.__name__)
            raise ArkeselError("SMS service is temporarily unavailable. Please try again.") from exc
        except requests.HTTPError as exc:
            logger.warning("Arkesel HTTP error: %s", exc.response.status_code if exc.response else "unknown")
            raise ArkeselError("SMS service is temporarily unavailable. Please try again.") from exc
        except requests.RequestException as exc:
            logger.warning("Arkesel request error: %s", exc.__class__.__name__)
            raise ArkeselError("SMS service is temporarily unavailable. Please try again.") from exc
