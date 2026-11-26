from xmender.services import discord, gmail, llm, pricing

HOOK = "https://discord.com/api/webhooks/123456789012345678/" + "t" * 68


def test_csrf_header_required(app_client):
    r = app_client.post("/api/auth/login", json={"username": "a", "password": "b"}, headers={"x-xmender": ""})
    assert r.status_code == 403


def test_setup_and_admin_rules(admin):
    c = admin
    st = c.get("/api/auth/state").json()
    assert st["setup_required"] is False and st["user"]["is_root"]
    # setup cannot be repeated
    assert c.post("/api/auth/setup", json={"temp_password": "x", "new_password": "y" * 12}).status_code == 409

    users = c.get("/api/admin/users").json()["users"]
    root = next(u for u in users if u["is_root"])
    assert c.delete(f"/api/admin/users/{root['id']}").status_code == 400
    assert c.patch(f"/api/admin/users/{root['id']}", json={"is_admin": False}).status_code == 400

    # registration off by default
    assert c.get("/api/admin/settings").json()["registration_enabled"] is False
    assert c.post("/api/auth/register", json={"username": "eve", "password": "x" * 12}).status_code == 403


def test_user_management(admin):
    c = admin
    r = c.post("/api/admin/users", json={"username": "bob", "password": "bob-password-1", "permissions": ["tasks"]})
    assert r.status_code == 200, r.text
    bob = r.json()["user"]
    assert bob["permissions"] == ["tasks"]
    r = c.patch(f"/api/admin/users/{bob['id']}", json={"is_admin": True})
    assert r.json()["user"]["is_admin"] is True
    assert c.delete(f"/api/admin/users/{bob['id']}").status_code == 200


def test_integrations_and_tasks(admin, monkeypatch):
    c = admin
    monkeypatch.setattr(gmail, "test_imap", lambda acct: (5, 100))
    smtp_calls = []
    monkeypatch.setattr(gmail, "test_smtp", lambda acct: smtp_calls.append(acct.email))
    monkeypatch.setattr(llm, "list_models", lambda key, refresh=False: [llm.ModelInfo("claude-opus-5-5", "Claude Opus 5.5", 128000)])
    sent = []
    monkeypatch.setattr(discord, "send_embed", lambda url, **kw: sent.append(url))

    r = c.post("/api/integrations/gmail", json={"name": "xMender", "email": "me+x@gmail.com", "password": "p"})
    assert r.status_code == 400
    r = c.post("/api/integrations/gmail", json={"name": "xMender", "email": "me@gmail.com", "password": "abcd efgh ijkl mnop"})
    assert r.status_code == 200, r.text
    g = r.json()["integration"]
    assert g["smtp_enabled"] is False and not smtp_calls

    r = c.patch(f"/api/integrations/gmail/{g['id']}/smtp", json={"enabled": True})
    assert r.json()["integration"]["smtp_enabled"] is True and smtp_calls == ["me@gmail.com"]

    r = c.post("/api/integrations/discord", json={"name": "Bot", "url": HOOK, "test": "skip"})
    assert r.status_code == 200 and not sent
    d = r.json()["integration"]
    r = c.post("/api/integrations/discord", json={"id": d["id"], "name": "Bot2", "test": "send"})
    assert r.status_code == 200 and len(sent) == 1

    steps = [{"type": "webhook_agent", "config": {"instructions": "sum", "discord_integration_id": d["id"]}}]
    r = c.post("/api/tasks", json={"name": "T", "gmail_integration_id": g["id"], "steps": steps})
    assert r.status_code == 400 and "Anthropic" in r.text

    assert c.post("/api/integrations/anthropic", json={"api_key": "sk-ant-test-123456"}).status_code == 200
    r = c.post("/api/tasks", json={"name": "T", "gmail_integration_id": g["id"], "steps": steps})
    assert r.status_code == 400 and "default model" in r.text
    assert c.put("/api/me/settings", json={"default_model": "nope"}).status_code == 400
    assert c.put("/api/me/settings", json={"default_model": "claude-opus-5-5"}).status_code == 200
    r = c.post("/api/tasks", json={"name": "T", "gmail_integration_id": g["id"], "steps": steps})
    assert r.status_code == 200, r.text

    # integrations in use cannot be deleted
    assert c.delete(f"/api/integrations/{d['id']}").status_code == 409
    assert c.delete(f"/api/integrations/{g['id']}").status_code == 409

    secrets = c.get("/api/integrations").text
    assert "abcdefghijklmnop" not in secrets and "t" * 68 not in secrets and "sk-ant-test-123456" not in secrets


def test_logout(admin):
    c = admin
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/tasks").status_code == 401
    r = c.post("/api/auth/login", json={"username": "ADMIN", "password": "correct-horse-1"})
    assert r.status_code == 200


def test_poller_processes_new_mail(admin, monkeypatch):
    from email.message import EmailMessage

    from xmender.services import poller

    msg = EmailMessage()
    msg["From"] = "billing@shop.com"
    msg["To"] = "me@gmail.com"
    msg["Subject"] = "Invoice 7"
    msg["Message-ID"] = "<inv7@shop.com>"
    msg.set_content("Amount due: 10")
    raw = msg.as_bytes()

    gid = admin.get("/api/integrations").json()["gmail"][0]["id"]
    seen = []
    monkeypatch.setattr(gmail, "fetch_new", lambda acct, v, last, limit: (
        seen.append((v, last)) or gmail.FetchResult(uidvalidity=5, last_uid=last, messages=[(101, raw)])))
    monkeypatch.setattr(llm, "list_models", lambda key, refresh=False: [llm.ModelInfo("claude-opus-5-5", "Claude Opus 5.5", 128000)])
    attempt = llm.UsageAttempt(
        "claude-opus-5-5", pricing.Tokens(input=1234, output=56, cache_read=100)
    )
    monkeypatch.setattr(llm, "complete", lambda key, model, s, u: llm.LLMResult(
        "Invoice 7 for $10", "end_turn", model, usage=(attempt,)))
    sent = []
    monkeypatch.setattr(discord, "send_embed", lambda url, **kw: sent.append(kw))

    s = poller.poll_integration(gid)
    assert s["new"] == 1 and s["runs"] == 1 and seen == [(5, 100)]
    assert sent and sent[0]["description"] == "Invoice 7 for $10"

    # same UID again is ignored (already stored), cursor advanced to 101
    s = poller.poll_integration(gid)
    assert seen[-1] == (5, 101) and s["runs"] == 0

    feed = admin.get("/api/emails").json()["emails"]
    assert feed[0]["subject"] == "Invoice 7" and feed[0]["runs"][0]["status"] == "completed"


def test_usage_report(admin):
    r = admin.get("/api/usage?period=today&tz=Europe/Stockholm").json()
    # 1234 * $4 + 56 * $20 + 100 * $0.20 per MTok = $0.006076
    assert r["total"]["requests"] == 1 and r["total"]["cost_nanousd"] == 6_076_000
    assert r["models"][0]["model"] == "claude-opus-5-5" and r["models"][0]["rates"]["input"] == "4"
    assert r["tasks"][0]["requests"] == 1 and len(r["days"]) == 1
    assert admin.get("/api/usage?period=all&scope=all").json()["total"]["requests"] == 1
    assert admin.get("/api/usage?period=bogus").status_code == 422

    feed = admin.get("/api/emails").json()["emails"]
    step = feed[0]["runs"][0]["log"][0]
    assert step["usage"]["cost_nanousd"] == 6_076_000


def test_my_settings_partial_update(admin):
    me = admin.put("/api/me/settings", json={"timezone": "Europe/Stockholm"}).json()["user"]
    # sending only the time zone keeps the default model
    assert me["timezone"] == "Europe/Stockholm" and me["default_model"] == "claude-opus-5-5"
    assert admin.put("/api/me/settings", json={"timezone": "Mars/Base"}).status_code == 400
    assert admin.get("/api/auth/state").json()["user"]["timezone"] == "Europe/Stockholm"


def test_poller_passes_sender_history(admin, monkeypatch):
    from email.message import EmailMessage

    from xmender.services import pipeline, poller

    msg = EmailMessage()
    msg["From"] = "Billing <BILLING@shop.com>"
    msg["To"] = "me@gmail.com"
    msg["Subject"] = "Invoice 8"
    msg.set_content("Amount due: 12")
    gid = admin.get("/api/integrations").json()["gmail"][0]["id"]
    monkeypatch.setattr(gmail, "fetch_new", lambda acct, v, last, limit: gmail.FetchResult(
        uidvalidity=5, last_uid=last, messages=[(102, msg.as_bytes())]))
    seen = []
    monkeypatch.setattr(pipeline, "run_task", lambda steps, mail, ctx: (
        seen.append(ctx.sender_seen) or pipeline.RunResult("completed", [])))
    poller.poll_integration(gid)
    # invoice 7 from the same address (different case) came earlier
    assert len(seen[0]) == 1 and seen[0][0].tzinfo is not None


def test_http_integration(admin, monkeypatch):
    from xmender.services import http_hook

    c = admin
    r = c.post("/api/integrations/http", json={"name": "LAN", "url": "http://192.168.1.10/hook", "test": "skip"})
    assert r.status_code == 400 and "private network" in r.text

    monkeypatch.setattr(http_hook, "check_url", lambda url, allow_private: "93.184.215.14")
    sent = []
    monkeypatch.setattr(http_hook, "send", lambda target, **kw: sent.append((target, kw)) or 200)
    r = c.post("/api/integrations/http", json={
        "name": "ntfy", "url": "https://ntfy.example/topic-s3cret", "method": "PUT", "test": "send",
        "headers": [{"name": "Authorization", "value": "Bearer tok-s3cret"}]})
    assert r.status_code == 200, r.text
    w = r.json()["integration"]
    assert w["method"] == "PUT" and w["headers"] == ["Authorization"] and sent[0][1]["method"] == "PUT"
    # edit: blank URL and blank header value keep the stored ones
    r = c.post("/api/integrations/http", json={"id": w["id"], "name": "ntfy2", "test": "skip",
                                               "headers": [{"name": "authorization", "value": ""}, {"name": "X-Extra", "value": "1"}]})
    assert r.status_code == 200, r.text
    from xmender.db import session_scope
    from xmender.models import Integration
    from xmender.services.accounts import http_target

    with session_scope() as db:
        t = http_target(db.get(Integration, w["id"]))
    assert t.url == "https://ntfy.example/topic-s3cret"
    assert t.headers == {"authorization": "Bearer tok-s3cret", "X-Extra": "1"}
    listing = c.get("/api/integrations").text
    assert "s3cret" not in listing and "ntfy.example" in listing

    gid = c.get("/api/integrations").json()["gmail"][0]["id"]
    steps = [{"type": "http_post", "config": {"http_integration_id": w["id"], "body": '{"s": "{{email.subject}}"}'}}]
    r = c.post("/api/tasks", json={"name": "H", "gmail_integration_id": gid, "steps": steps})
    assert r.status_code == 200, r.text
    assert c.get("/api/tasks/meta").json()["http"] == [{"id": w["id"], "name": "ntfy2"}]
    assert c.delete(f"/api/integrations/{w['id']}").status_code == 409
