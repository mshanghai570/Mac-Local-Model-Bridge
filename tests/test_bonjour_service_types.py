from local_ai_gateway.discovery.bonjour import BonjourAdvertiser


def test_advertised_service_type_respects_dns_sd_label_limit():
    """Avoid zeroconf's BadTypeInNameException on the Mac gateway."""
    assert BonjourAdvertiser.SERVICE_TYPES == ["_local-ai-bridge._tcp"]
    for service_type in BonjourAdvertiser.SERVICE_TYPES:
        service_label = service_type.split(".", 1)[0].lstrip("_").encode("utf-8")
        assert len(service_label) <= 15
