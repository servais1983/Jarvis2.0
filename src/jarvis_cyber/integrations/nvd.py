from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import httpx

from jarvis_cyber.config import settings
from jarvis_cyber.core.schemas import CVERecord, CVEReference


class CVENotFoundError(ValueError):
    """Raised when the requested CVE is absent from the upstream source."""


class NVDClient:
    """Minimal client for the official NVD CVE API."""

    def __init__(
        self,
        *,
        base_url: str = settings.nvd_base_url,
        api_key: str | None = (
            settings.nvd_api_key.get_secret_value() if settings.nvd_api_key else None
        ),
        timeout_seconds: float = settings.http_timeout_seconds,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client

    def fetch_cve(self, cve_id: str) -> CVERecord:
        headers = {"apiKey": self.api_key} if self.api_key else {}

        if self._client is not None:
            response = self._client.get(
                self.base_url,
                params={"cveId": cve_id},
                headers=headers,
            )
        else:
            response = httpx.get(
                self.base_url,
                params={"cveId": cve_id},
                headers=headers,
                timeout=self.timeout_seconds,
            )

        response.raise_for_status()
        payload = response.json()
        vulnerabilities = payload.get("vulnerabilities", [])
        if not vulnerabilities:
            raise CVENotFoundError(cve_id)

        cve = vulnerabilities[0]["cve"]
        description = self._pick_english_description(cve.get("descriptions", []))
        score, severity = self._extract_cvss(cve.get("metrics", {}))

        return CVERecord(
            cve_id=cve["id"],
            status=cve.get("vulnStatus"),
            published=cve.get("published"),
            last_modified=cve.get("lastModified"),
            description=description,
            cvss_score=score,
            cvss_severity=severity,
            known_exploited=bool(cve.get("cisaExploitAdd")),
            required_action=cve.get("cisaRequiredAction"),
            affected_criteria=self._extract_criteria(cve.get("configurations", [])),
            references=[
                CVEReference(
                    url=reference["url"],
                    source=reference.get("source"),
                    tags=reference.get("tags", []),
                )
                for reference in cve.get("references", [])
            ],
        )

    def search_recent_cves(
        self,
        *,
        keywords: str,
        published_from: datetime,
        published_to: datetime,
        exact_match: bool = False,
        kev_only: bool = False,
        limit: int = 5,
    ) -> list[CVERecord]:
        headers = {"apiKey": self.api_key} if self.api_key else {}
        params: dict[str, str | int] = {
            "keywordSearch": keywords,
            "pubStartDate": published_from.isoformat(),
            "pubEndDate": published_to.isoformat(),
            "resultsPerPage": limit,
        }
        if exact_match:
            params["keywordExactMatch"] = ""
        if kev_only:
            params["hasKev"] = ""

        if self._client is not None:
            response = self._client.get(self.base_url, params=params, headers=headers)
        else:
            response = httpx.get(
                self.base_url,
                params=params,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
        return [
            self._record_from_payload(item["cve"])
            for item in payload.get("vulnerabilities", [])[:limit]
        ]

    @staticmethod
    def _pick_english_description(descriptions: Iterable[dict]) -> str:
        for description in descriptions:
            if description.get("lang") == "en":
                return description["value"]
        first = next(iter(descriptions), None)
        return first["value"] if first else ""

    @staticmethod
    def _extract_cvss(metrics: dict) -> tuple[float | None, str | None]:
        for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            if key not in metrics:
                continue
            first_metric = metrics[key][0]
            cvss_data = first_metric.get("cvssData", {})
            score = cvss_data.get("baseScore")
            severity = cvss_data.get("baseSeverity") or first_metric.get("baseSeverity")
            return score, severity
        return None, None

    @classmethod
    def _extract_criteria(cls, configurations: list[dict]) -> list[str]:
        criteria: list[str] = []
        for configuration in configurations:
            for node in configuration.get("nodes", []):
                criteria.extend(cls._extract_criteria_from_node(node))
        return criteria

    @classmethod
    def _extract_criteria_from_node(cls, node: dict) -> list[str]:
        criteria = [
            match["criteria"]
            for match in node.get("cpeMatch", [])
            if match.get("vulnerable") and match.get("criteria")
        ]
        for child in node.get("children", []):
            criteria.extend(cls._extract_criteria_from_node(child))
        return criteria

    def _record_from_payload(self, cve: dict) -> CVERecord:
        description = self._pick_english_description(cve.get("descriptions", []))
        score, severity = self._extract_cvss(cve.get("metrics", {}))
        return CVERecord(
            cve_id=cve["id"],
            status=cve.get("vulnStatus"),
            published=cve.get("published"),
            last_modified=cve.get("lastModified"),
            description=description,
            cvss_score=score,
            cvss_severity=severity,
            known_exploited=bool(cve.get("cisaExploitAdd")),
            required_action=cve.get("cisaRequiredAction"),
            affected_criteria=self._extract_criteria(cve.get("configurations", [])),
            references=[
                CVEReference(
                    url=reference["url"],
                    source=reference.get("source"),
                    tags=reference.get("tags", []),
                )
                for reference in cve.get("references", [])
            ],
        )


nvd_client = NVDClient()
