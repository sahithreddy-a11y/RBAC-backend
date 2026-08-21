from day4_review_target import EntitlementService


def test_authorize_fails_closed_when_verification_errors():
    service = EntitlementService(
        jwks={"keys": []},
        issuer="issuer",
        audience="audience",
        orgs={},
        cache={},
    )

    def failing_verify(token):
        raise RuntimeError("verification service unavailable")

    service.verify = failing_verify

    result = service.authorize(
        "test-token",
        "org-1",
        ["fcs", "nta"],
    )

    assert result.allowed is False
    assert result.modules == []