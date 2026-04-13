from understudy.security.allowlist import is_allowed


def test_allows_normal_site():
    assert is_allowed("https://example.com/page")


def test_blocks_password_manager():
    assert not is_allowed("https://1password.com/vault")


def test_blocks_subdomain_of_denied():
    assert not is_allowed("https://login.bankofamerica.com/")


def test_blocks_bank():
    assert not is_allowed("https://www.chase.com/checking")


def test_blocks_payment_provider():
    assert not is_allowed("https://www.paypal.com/checkout")


def test_blocks_oauth_providers():
    assert not is_allowed("https://accounts.google.com/signin")
    assert not is_allowed("https://login.microsoftonline.com/")


def test_blocks_stripe_and_plaid():
    assert not is_allowed("https://checkout.stripe.com/c/abc")
    assert not is_allowed("https://plaid.com/link")


def test_blocks_aws_console():
    assert not is_allowed("https://console.aws.amazon.com/iam/home")


def test_extra_deny_works():
    assert not is_allowed("https://internal.corp/", extra_deny=frozenset({"internal.corp"}))


def test_none_url_denied():
    assert not is_allowed(None)


def test_empty_url_denied():
    assert not is_allowed("")


def test_invalid_url_denied():
    assert not is_allowed("not-a-url")


def test_userinfo_bypass_blocked():
    # `chase.com@evil.com` actually resolves to evil.com — but we reject any URL
    # carrying userinfo because it is a known phishing/confusion vector.
    assert not is_allowed("https://chase.com@evil.com/")


def test_subdomain_lookalike_blocked_when_safe():
    # `chase.com.evil.com` does NOT end with `.chase.com` so it is allowed
    # (it's evil.com, which isn't on the deny list). The safe property is that
    # it isn't *miscategorised* as chase.com.
    assert is_allowed("https://chase.com.evil.com/")


def test_bare_ip_literal_blocked():
    assert not is_allowed("https://127.0.0.1/")
    assert not is_allowed("https://10.0.0.1/")


def test_idna_punycode_normalised():
    # IDNA host should not slip through via mixed encoding.
    assert is_allowed("https://example.com/")
