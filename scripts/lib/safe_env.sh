#!/usr/bin/env bash
# safe_env — run a command with a hardened environment.
#
# Replaces the older ``env -u FOO -u BAR ...`` blocklist pattern used
# when invoking subscription-CLI tools (claude / gemini / codex).
# A blocklist requires enumerating every auth/routing variable each
# CLI honors — open-ended and silently grows with each CLI release.
#
# This allowlist inverts the burden: only the explicitly listed
# variables cross the boundary; everything else (including future
# *_API_KEY / *_AUTH_TOKEN / *_BASE_URL / dotenv-loaded overrides)
# is dropped by default.
#
# What stays: HOME (subscription tokens live in ~/.claude /
# ~/.config/gcloud / ~/.codex), PATH (to find the CLI), locale/term
# (so help output is readable), XDG paths (subscription tokens on
# Linux), tempdir, proxy vars (corporate networks need them or
# reviewers can't reach their backends), TLS cert paths (custom CA
# bundles for intercepting proxies), DISPLAY (first-time OAuth flow
# may need to open a browser).
# What goes: every *_API_KEY, *_TOKEN, *_BASE_URL, *_PROJECT,
# *_LOCATION, GOOGLE_APPLICATION_CREDENTIALS, dotenv inputs, et al.
#
# Pinned by tests/unit/test_safe_env_contract.py.

safe_env() {
    # Round-11 review-tooling close-out: when neither SSL_CERT_FILE
    # nor SSL_CERT_DIR is set in the parent shell, codex-cli's Rust
    # HTTP stack fails with "no native root CA certificates found"
    # inside our env -i sandbox — rustls can't auto-enumerate
    # /etc/ssl/certs/* the way curl/openssl do. Auto-discover the
    # distro's system CA bundle so the inner CLI can validate TLS.
    # This is benign: it routes validation through the same trust
    # store the parent shell already uses; it does NOT introduce
    # any auth/billing path (subscription auth still lives in
    # ~/.codex / ~/.config/gcloud / ~/.claude).
    local _safe_env_ssl_cert="${SSL_CERT_FILE:-}"
    if [ -z "$_safe_env_ssl_cert" ] && [ -z "${SSL_CERT_DIR:-}" ]; then
        for _cand in \
            /etc/ssl/certs/ca-certificates.crt \
            /etc/pki/tls/certs/ca-bundle.crt \
            /etc/ssl/cert.pem; do
            if [ -r "$_cand" ]; then _safe_env_ssl_cert="$_cand"; break; fi
        done
    fi
    env -i \
        HOME="$HOME" \
        PATH="$PATH" \
        USER="${USER:-}" \
        SHELL="${SHELL:-/bin/sh}" \
        TERM="${TERM:-dumb}" \
        LANG="${LANG:-}" \
        LC_ALL="${LC_ALL:-}" \
        TMPDIR="${TMPDIR:-/tmp}" \
        XDG_DATA_HOME="${XDG_DATA_HOME:-}" \
        XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-}" \
        XDG_CACHE_HOME="${XDG_CACHE_HOME:-}" \
        XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
        HTTP_PROXY="${HTTP_PROXY:-}" \
        HTTPS_PROXY="${HTTPS_PROXY:-}" \
        NO_PROXY="${NO_PROXY:-}" \
        ALL_PROXY="${ALL_PROXY:-}" \
        http_proxy="${http_proxy:-}" \
        https_proxy="${https_proxy:-}" \
        no_proxy="${no_proxy:-}" \
        all_proxy="${all_proxy:-}" \
        SSL_CERT_FILE="$_safe_env_ssl_cert" \
        SSL_CERT_DIR="${SSL_CERT_DIR:-}" \
        REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-}" \
        CURL_CA_BUNDLE="${CURL_CA_BUNDLE:-}" \
        NODE_EXTRA_CA_CERTS="${NODE_EXTRA_CA_CERTS:-}" \
        DISPLAY="${DISPLAY:-}" \
        WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
        "$@"
}
