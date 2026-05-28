from __future__ import annotations

from jarvis_cyber.core.schemas import SentinelQueryTemplate


SENTINEL_QUERY_TEMPLATES = [
    SentinelQueryTemplate(
        template_id="account-signin-overview",
        name="Connexions récentes d'un compte",
        category="account_compromise",
        description="Liste les connexions récentes d'un utilisateur avec IP, application, résultat et risque.",
        parameters=["user_principal_name"],
        default_timespan="P7D",
        query_template="""SigninLogs
| where UserPrincipalName =~ '[[user_principal_name]]'
| project TimeGenerated, UserPrincipalName, IPAddress, AppDisplayName, ResultType, ResultDescription,
          ConditionalAccessStatus, RiskLevelAggregated, RiskState, Location
| order by TimeGenerated desc
| take 50""",
    ),
    SentinelQueryTemplate(
        template_id="account-risky-signins",
        name="Connexions risquées d'un compte",
        category="account_compromise",
        description="Isole les connexions avec signaux de risque pour un utilisateur.",
        parameters=["user_principal_name"],
        default_timespan="P14D",
        query_template="""SigninLogs
| where UserPrincipalName =~ '[[user_principal_name]]'
| where RiskLevelAggregated !in ('none', 'hidden', '')
   or RiskState !in ('none', '')
| project TimeGenerated, UserPrincipalName, IPAddress, AppDisplayName, RiskLevelAggregated,
          RiskState, RiskDetail, ResultType, Location
| order by TimeGenerated desc
| take 50""",
    ),
    SentinelQueryTemplate(
        template_id="phishing-recipient-email-events",
        name="Emails reçus par un destinataire",
        category="phishing",
        description="Recherche les emails reçus par un utilisateur pour qualifier une exposition phishing.",
        parameters=["recipient"],
        default_timespan="P7D",
        query_template="""EmailEvents
| where RecipientEmailAddress =~ '[[recipient]]'
| project TimeGenerated, RecipientEmailAddress, SenderFromAddress, SenderIPv4,
          Subject, DeliveryAction, ThreatTypes, DetectionMethods, NetworkMessageId
| order by TimeGenerated desc
| take 50""",
    ),
    SentinelQueryTemplate(
        template_id="phishing-url-clicks",
        name="Clics URL suspects",
        category="phishing",
        description="Recherche les événements d'URL liés à un domaine ou fragment d'URL suspect.",
        parameters=["url_fragment"],
        default_timespan="P7D",
        query_template="""UrlClickEvents
| where Url contains '[[url_fragment]]'
| project TimeGenerated, AccountUpn, Url, ActionType, Workload, ThreatTypes, IPAddress
| order by TimeGenerated desc
| take 50""",
    ),
    SentinelQueryTemplate(
        template_id="malware-device-processes",
        name="Processus suspects sur un appareil",
        category="malware",
        description="Liste les processus observés sur un appareil pour reconstruire une chaîne d'exécution.",
        parameters=["device_name"],
        default_timespan="P3D",
        query_template="""DeviceProcessEvents
| where DeviceName =~ '[[device_name]]'
| project TimeGenerated, DeviceName, AccountName, FileName, ProcessCommandLine,
          InitiatingProcessFileName, InitiatingProcessCommandLine, SHA256
| order by TimeGenerated desc
| take 100""",
    ),
    SentinelQueryTemplate(
        template_id="malware-powershell",
        name="PowerShell suspect",
        category="malware",
        description="Recherche les exécutions PowerShell avec indicateurs souvent associés à des abus.",
        parameters=["device_name"],
        default_timespan="P7D",
        query_template="""DeviceProcessEvents
| where DeviceName =~ '[[device_name]]'
| where FileName in~ ('powershell.exe', 'pwsh.exe')
| where ProcessCommandLine has_any ('EncodedCommand', '-enc', 'Invoke-WebRequest', 'IEX', 'DownloadString')
| project TimeGenerated, DeviceName, AccountName, FileName, ProcessCommandLine,
          InitiatingProcessFileName, InitiatingProcessCommandLine
| order by TimeGenerated desc
| take 50""",
    ),
    SentinelQueryTemplate(
        template_id="data-exfil-cloud-activity",
        name="Activité cloud volumineuse d'un compte",
        category="data_exfiltration",
        description="Recherche des activités cloud récentes d'un compte pouvant soutenir une hypothèse d'exfiltration.",
        parameters=["account"],
        default_timespan="P7D",
        query_template="""CloudAppEvents
| where AccountDisplayName has '[[account]]' or AccountId has '[[account]]'
| project TimeGenerated, Application, ActionType, AccountDisplayName, IPAddress,
          ObjectName, RawEventData
| order by TimeGenerated desc
| take 100""",
    ),
    SentinelQueryTemplate(
        template_id="critical-cve-device-exposure",
        name="Exposition appareil par CVE",
        category="critical_vulnerability",
        description="Recherche les appareils exposés à une CVE dans les données Defender TVM.",
        parameters=["cve_id"],
        default_timespan="P30D",
        query_template="""DeviceTvmSoftwareVulnerabilities
| where CveId =~ '[[cve_id]]'
| project DeviceName, OSPlatform, SoftwareVendor, SoftwareName, SoftwareVersion,
          CveId, VulnerabilitySeverityLevel, RecommendedSecurityUpdate
| take 100""",
    ),
]


def list_sentinel_query_templates() -> list[SentinelQueryTemplate]:
    return SENTINEL_QUERY_TEMPLATES


def get_sentinel_query_template(template_id: str) -> SentinelQueryTemplate | None:
    return next((item for item in SENTINEL_QUERY_TEMPLATES if item.template_id == template_id), None)


def render_sentinel_query_template(
    template: SentinelQueryTemplate,
    parameters: dict[str, str],
) -> str:
    query = template.query_template
    for name in template.parameters:
        value = parameters.get(name)
        if value is None or value == "":
            raise ValueError(f"Missing required parameter: {name}")
        query = query.replace(f"[[{name}]]", _escape_kql_string(value))
    return query


def _escape_kql_string(value: str) -> str:
    return value.replace("'", "''")
