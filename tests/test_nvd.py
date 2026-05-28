from datetime import UTC, datetime

import httpx

from jarvis_cyber.integrations.nvd import NVDClient


def test_nvd_client_parses_record() -> None:
    payload = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-0001",
                    "vulnStatus": "Analyzed",
                    "published": "2026-05-01T12:00:00.000",
                    "lastModified": "2026-05-02T12:00:00.000",
                    "descriptions": [{"lang": "en", "value": "Remote code execution."}],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}
                        ]
                    },
                    "cisaExploitAdd": "2026-05-03",
                    "cisaRequiredAction": "Apply vendor updates.",
                    "configurations": [
                        {
                            "nodes": [
                                {
                                    "cpeMatch": [
                                        {
                                            "vulnerable": True,
                                            "criteria": "cpe:2.3:a:vendor:product:*:*:*:*:*:*:*:*",
                                        }
                                    ]
                                }
                            ]
                        }
                    ],
                    "references": [
                        {"url": "https://example.com/advisory", "source": "vendor", "tags": ["Patch"]}
                    ],
                }
            }
        ]
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    client = httpx.Client(transport=transport)

    record = NVDClient(client=client).fetch_cve("CVE-2026-0001")

    assert record.cve_id == "CVE-2026-0001"
    assert record.cvss_score == 9.8
    assert record.cvss_severity == "CRITICAL"
    assert record.known_exploited is True
    assert record.affected_criteria


def test_nvd_client_searches_recent_cves() -> None:
    payload = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-0002",
                    "descriptions": [{"lang": "en", "value": "Microsoft Outlook issue."}],
                    "metrics": {},
                    "references": [],
                }
            }
        ]
    }
    observed_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed_params.update(request.url.params)
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    records = NVDClient(client=client).search_recent_cves(
        keywords="Microsoft Outlook",
        published_from=datetime(2026, 5, 15, tzinfo=UTC),
        published_to=datetime(2026, 5, 16, tzinfo=UTC),
        exact_match=True,
        kev_only=True,
        limit=5,
    )

    assert records[0].cve_id == "CVE-2026-0002"
    assert observed_params["keywordSearch"] == "Microsoft Outlook"
    assert "keywordExactMatch" in observed_params
    assert "hasKev" in observed_params
