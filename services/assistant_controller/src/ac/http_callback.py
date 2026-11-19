"""HTTP POST of measurement results back to QLBN."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ac.models import ResultsCallback

logger = logging.getLogger(__name__)


class HttpCallbackClient:
    def __init__(
        self,
        timeout_seconds: float = 10.0,
        *,
        max_attempts: int = 3,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        self.timeout = timeout_seconds
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))

    def post_results(
        self,
        callback_url: str,
        results: ResultsCallback,
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id
        body = results.model_dump(mode="json")
        logger.info("POST results → %s session=%s", callback_url, results.session_id)
        with httpx.Client(timeout=self.timeout) as client:
            for attempt in range(1, self.max_attempts + 1):
                try:
                    resp = client.post(callback_url, json=body, headers=headers)
                    # A callback is successful only on 2xx. In particular, do
                    # not mistake a Coder/login 3xx redirect for acceptance.
                    if not 200 <= resp.status_code < 300:
                        resp.raise_for_status()
                    try:
                        return resp.json()
                    except Exception:  # noqa: BLE001
                        return {"status_code": resp.status_code, "text": resp.text}
                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    transient_status = (
                        exc.response.status_code
                        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None
                        else None
                    )
                    # Until every Frappe deployment advertises idempotency, do
                    # not retry an ambiguous read/write failure: the server may
                    # already have committed. Connection/pool timeouts happen
                    # before a response can be committed and are safe to retry.
                    retryable_transport = isinstance(
                        exc,
                        (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout),
                    )
                    retryable = (
                        retryable_transport
                        if transient_status is None
                        else transient_status in (408, 425, 429) or transient_status >= 500
                    )
                    if not retryable or attempt >= self.max_attempts:
                        raise
                    delay = self.retry_delay_seconds * attempt
                    logger.warning(
                        "Results callback attempt %d/%d failed; retrying in %.1fs: %s",
                        attempt,
                        self.max_attempts,
                        delay,
                        exc,
                    )
                    if delay:
                        time.sleep(delay)

        raise RuntimeError("results callback exhausted without a response")
