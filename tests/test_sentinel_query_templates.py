from jarvis_cyber.sentinel_queries.templates import (
    get_sentinel_query_template,
    list_sentinel_query_templates,
    render_sentinel_query_template,
)


def test_sentinel_query_template_library_contains_core_scenarios() -> None:
    categories = {template.category for template in list_sentinel_query_templates()}

    assert {
        "account_compromise",
        "phishing",
        "malware",
        "data_exfiltration",
        "critical_vulnerability",
    } <= categories


def test_sentinel_query_template_renderer_escapes_kql_strings() -> None:
    template = get_sentinel_query_template("account-signin-overview")
    assert template is not None

    query = render_sentinel_query_template(
        template,
        {"user_principal_name": "o'hara@example.com"},
    )

    assert "o''hara@example.com" in query
