from understudy.security.redact import redact


def test_credit_card_luhn_pass():
    out = redact("card 4242 4242 4242 4242 ok")
    assert "REDACTED:credit_card_loose" in out.text


def test_credit_card_random_digits_kept():
    # Non-Luhn digit sequence must NOT be redacted.
    out = redact("order 1234 5678 9012 3456")
    assert "1234 5678 9012 3456" in out.text


def test_jwt_redacted():
    jwt = "eyJ" + "a" * 20 + "." + "b" * 20 + "." + "c" * 20
    out = redact(f"token={jwt} done")
    assert "REDACTED:jwt" in out.text


def test_anthropic_key_redacted():
    out = redact("key sk-ant-" + "A" * 40)
    assert "REDACTED:anthropic_key" in out.text


def test_openai_proj_key_redacted():
    out = redact("key sk-proj-" + "A" * 40)
    assert "REDACTED:openai_proj_key" in out.text


def test_openai_svc_key_redacted():
    out = redact("key sk-svcacct-" + "A" * 40)
    assert "REDACTED:openai_svc_key" in out.text


def test_github_token_redacted():
    out = redact("ghp_" + "a" * 36)
    assert "REDACTED:github_pat" in out.text


def test_stripe_key_redacted():
    out = redact("sk_live_" + "a" * 30)
    assert "REDACTED:stripe_key" in out.text


def test_google_api_key_redacted():
    out = redact("AIza" + "A" * 35)
    assert "REDACTED:google_api_key" in out.text


def test_email_redacted():
    out = redact("ping me at hi@example.com tomorrow")
    assert "REDACTED:email" in out.text


def test_otp_redacted():
    out = redact("Your verification code: 938271")
    assert "REDACTED:otp" in out.text


def test_empty_input():
    out = redact("")
    assert out.text == ""
    assert out.changed is False


def test_none_input():
    out = redact(None)
    assert out.text == ""
    assert out.changed is False


def test_password_field_form():
    out = redact("password = hunter2")
    assert "REDACTED:password_field" in out.text


def test_aws_access_key():
    out = redact("AKIAIOSFODNN7EXAMPLE")
    assert "REDACTED:aws_access_key" in out.text


def test_aws_secret_key_labelled():
    out = redact("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
    assert "REDACTED:aws_secret_key_labelled" in out.text


def test_private_key_block_marker():
    out = redact("-----BEGIN PRIVATE KEY-----")
    assert "REDACTED:private_key" in out.text


def test_no_change_for_clean_text():
    s = "This is a normal sentence about agents and automation."
    out = redact(s)
    assert out.text == s
    assert out.changed is False
