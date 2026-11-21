"""Optional free notification channels, configured only through environment variables. Never raises; never prints secrets.
ntfy (NTFY_TOPIC [+NTFY_SERVER]), Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID), e-mail (SMTP_HOST, SMTP_PORT, SMTP_USER,
SMTP_PASSWORD, SMTP_FROM, SMTP_TO), generic webhook (WEBHOOK_URL, https only; posts {"text":..., "content":...})."""
import logging
import os
import re
import smtplib
from email.message import EmailMessage

import requests

log = logging.getLogger(__name__)
SECRET_KEYS = ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_PASSWORD", "SMTP_USER", "WEBHOOK_URL")
MAX_LEN = 3500


def _g(env, k):
    return (env.get(k) or "").strip()


def configured(env=None):
    env = os.environ if env is None else env
    out = []
    if _g(env, "NTFY_TOPIC"):
        out.append("ntfy")
    if _g(env, "TELEGRAM_BOT_TOKEN") and _g(env, "TELEGRAM_CHAT_ID"):
        out.append("telegram")
    if _g(env, "SMTP_HOST") and _g(env, "SMTP_TO"):
        out.append("email")
    if _g(env, "WEBHOOK_URL"):
        out.append("webhook")
    return out


def _scrub(msg, env):
    msg = str(msg)
    for k in SECRET_KEYS:
        v = _g(env, k)
        if v:
            msg = msg.replace(v, "***")
    return msg[:300]


def _ntfy(text, title, env):
    topic, server = _g(env, "NTFY_TOPIC"), (_g(env, "NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic) or not server.startswith("https://"):
        raise ValueError("NTFY_TOPIC must be letters/digits/-/_ (max 64) and NTFY_SERVER must be https")
    requests.post(f"{server}/{topic}", data=text.encode("utf-8"), headers={"Title": title.encode("ascii", "ignore").decode()}, timeout=10).raise_for_status()


def _telegram(text, title, env):
    requests.post(f"https://api.telegram.org/bot{_g(env, 'TELEGRAM_BOT_TOKEN')}/sendMessage", json={"chat_id": _g(env, "TELEGRAM_CHAT_ID"), "text": text[:4000]}, timeout=10).raise_for_status()


def _email(text, title, env):
    host, port = _g(env, "SMTP_HOST"), int(_g(env, "SMTP_PORT") or 587)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = title, _g(env, "SMTP_FROM") or _g(env, "SMTP_USER") or "scout@localhost", _g(env, "SMTP_TO")
    msg.set_content(text)
    cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with cls(host, port, timeout=15) as srv:
        if cls is smtplib.SMTP and port != 25:
            srv.starttls()
        if _g(env, "SMTP_USER"):
            srv.login(_g(env, "SMTP_USER"), _g(env, "SMTP_PASSWORD"))
        srv.send_message(msg)


def _webhook(text, title, env):
    url = _g(env, "WEBHOOK_URL")
    if not url.startswith("https://"):
        raise ValueError("WEBHOOK_URL must start with https://")
    requests.post(url, json={"text": text, "content": text}, timeout=10).raise_for_status()


SENDERS = {"ntfy": _ntfy, "telegram": _telegram, "email": _email, "webhook": _webhook}


def send(text, title="Multibagger Scout AI", env=None):
    """Returns [{channel, ok, error}] for every configured channel (empty list = none configured)."""
    env = os.environ if env is None else env
    text = text if len(text) <= MAX_LEN else text[: MAX_LEN - 20] + "\n...(truncated)"
    results = []
    for ch in configured(env):
        try:
            SENDERS[ch](text, title, env)
            results.append({"channel": ch, "ok": True, "error": None})
        except Exception as exc:
            err = _scrub(f"{type(exc).__name__}: {exc}", env)
            log.warning("notification channel %s failed: %s", ch, err)
            results.append({"channel": ch, "ok": False, "error": err})
    return results
