from xmender.services import discord, gmail, llm, pricing

HOOK = "https://discord.com/api/webhooks/123456789012345678/" + "t" * 68


def test_csrf_header_required(app_client):
    r = app_client.post("/api/auth/login", json={"username": "a", "password": "b"}, headers={"x-xmender": ""})
    assert r.status_code == 403


def test_pwa_assets(app_client):
    import json
    import re

    r = app_client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    m = json.loads(r.text)
    assert m["start_url"] == "/" and m["scope"] == "/" and m["display"] == "standalone"
    sizes = {(i["sizes"], i.get("purpose", "any")) for i in m["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= sizes
    for icon in m["icons"]:
        assert app_client.get(icon["src"]).status_code == 200, icon["src"]

    sw = app_client.get("/sw.js")
    assert sw.status_code == 200
    assert "javascript" in sw.headers["content-type"]
    assert sw.headers["cache-control"] == "no-cache"
    for path in re.findall(r"'(/[^']*)',", sw.text.split("];")[0]):
        assert app_client.get(path).status_code == 200, path

    for page in ("/", "/docs"):
        html = app_client.get(page).text
        for ref in ("/manifest.webmanifest", "/static/pwa.js", "apple-touch-icon", "theme-color"):
            assert ref in html, (page, ref)
        for src in re.findall(r'href="(/static/icons/[^"]+)"', html):
            assert app_client.get(src).status_code == 200, src


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

    r = c.post("/api/integrations/anthropic", json={"api_key": "sk-ant-test-123456"})
    assert r.status_code == 200
    a = r.json()["integration"]
    assert a["key_prefix"] == "sk-ant-" and a["key_hint"] == "sk-ant-…3456"

    # The address is masked everywhere; only the integrations list has it in full.
    gi = c.get("/api/integrations").json()["gmail"][0]
    assert gi["email"] == "me@gmail.com" and gi["email_masked"] == "**@gmail.com"
    assert "from_name" not in gi
    assert c.get("/api/status").json()["inboxes"][0]["email"] == "**@gmail.com"
    assert c.get("/api/tasks/meta").json()["gmail"][0]["email"] == "**@gmail.com"
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
    monkeypatch.setattr(pipeline, "run_task", lambda steps, mail, ctx, **kw: (
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


def test_poller_passes_gmail_labels(admin, monkeypatch):
    from email.message import EmailMessage

    from xmender.services import pipeline, poller

    msg = EmailMessage()
    msg["From"] = "deals@shop.com"
    msg["Subject"] = "Sale"
    msg.set_content("50% off")
    gid = admin.get("/api/integrations").json()["gmail"][0]["id"]
    monkeypatch.setattr(gmail, "fetch_new", lambda acct, v, last, limit: gmail.FetchResult(
        uidvalidity=5, last_uid=last, messages=[(103, msg.as_bytes())],
        gmail_meta={103: {"labels": ["\\Inbox"], "category": "promotions"}}))
    seen = []
    monkeypatch.setattr(pipeline, "run_task", lambda steps, mail, ctx, **kw: (
        seen.append((mail.labels, mail.category)) or pipeline.RunResult("completed", [])))
    poller.poll_integration(gid)
    assert seen and seen[0] == (["\\Inbox"], "promotions")


def test_task_chains(admin, monkeypatch):
    from email.message import EmailMessage

    from xmender.services import poller

    c = admin
    monkeypatch.setattr(gmail, "test_imap", lambda acct: (9, 10))
    first = c.get("/api/integrations").json()["gmail"][0]["id"]
    gid = c.post("/api/integrations/gmail", json={
        "name": "Chains", "email": "chain@gmail.com", "password": "abcd efgh ijkl mnop"}).json()["integration"]["id"]
    did = c.get("/api/integrations").json()["discord"][0]["id"]
    post = lambda body: {"type": "template_post", "config": {"discord_integration_id": did, "body": body}}

    a = c.post("/api/tasks", json={"name": "A", "gmail_integration_id": gid, "steps": [
        {"type": "filter_builtin", "name": "inv", "config": {"subject": "invoice"}}, post("A")]}).json()["task"]
    assert a["depends_on"] is None
    # B runs after A completed and may use A's step names
    body = {"name": "B", "gmail_integration_id": gid, "steps": [post("B {{inv.matched}}")],
            "depends_on": {"task_id": a["id"], "status": ["completed", "bogus"]}}
    r = c.post("/api/tasks", json=body)
    assert r.status_code == 200, r.text
    b = r.json()["task"]
    assert b["depends_on"] == {"task_id": a["id"], "status": ["completed"]}
    # C is the "else" branch: runs when A stopped
    cc = c.post("/api/tasks", json={"name": "C", "gmail_integration_id": gid, "steps": [post("C")],
                                    "depends_on": {"task_id": a["id"], "status": ["stopped"]}}).json()["task"]

    # name clash with an inherited step, other inbox, no status, loop
    clash = {**body, "steps": [{**post("x"), "name": "inv"}]}
    assert "earlier task" in c.post("/api/tasks", json=clash).text
    assert "same inbox" in c.post("/api/tasks", json={**body, "gmail_integration_id": first}).text
    assert "at least one" in c.post("/api/tasks", json={**body, "depends_on": {"task_id": a["id"], "status": []}}).text
    r = c.put(f"/api/tasks/{a['id']}", json={**a, "depends_on": {"task_id": b["id"]}})
    assert r.status_code == 400 and "loop" in r.text
    # renaming `inv` in A rewrites B's placeholder
    task = lambda tid: next(t for t in c.get("/api/tasks").json()["tasks"] if t["id"] == tid)
    renamed = [{**a["steps"][0], "name": "invoice"}, a["steps"][1]]
    r = c.put(f"/api/tasks/{a['id']}", json={**a, "steps": renamed, "renames": {"inv": "invoice"}})
    assert r.status_code == 200, r.text
    assert r.json()["chain"] == {"updated": ["B"], "paused": [], "fixed": []}
    assert task(b["id"])["steps"][0]["config"]["body"] == "B {{invoice.matched}}"
    r = c.put(f"/api/tasks/{a['id']}", json={**a, "renames": {"invoice": "inv"}})
    assert r.status_code == 200 and task(b["id"])["steps"][0]["config"]["body"] == "B {{inv.matched}}"
    # dropping `inv` breaks B: refused unless forced, then B is paused until fixed
    r = c.put(f"/api/tasks/{a['id']}", json={**a, "steps": [post("A")]})
    assert r.status_code == 409 and r.json()["detail"]["broken"][0]["name"] == "B"
    r = c.put(f"/api/tasks/{a['id']}", json={**a, "steps": [post("A")], "force": True})
    assert r.json()["chain"]["paused"] == ["B"] and "`inv`" in task(b["id"])["broken"]
    r = c.put(f"/api/tasks/{a['id']}", json=a)
    assert r.json()["chain"]["fixed"] == ["B"] and task(b["id"])["broken"] is None
    assert c.delete(f"/api/tasks/{a['id']}").status_code == 409

    sent = []
    monkeypatch.setattr(discord, "send_embed", lambda url, **kw: sent.append(kw["description"]))

    def deliver(uid, subject):
        msg = EmailMessage()
        msg["From"] = "x@shop.com"
        msg["Subject"] = subject
        msg.set_content("hi")
        monkeypatch.setattr(gmail, "fetch_new", lambda acct, v, last, limit: gmail.FetchResult(
            uidvalidity=9, last_uid=last, messages=[(uid, msg.as_bytes())]))
        assert poller.poll_integration(gid)["runs"] == 3
        return {r["task_name"]: r for r in c.get("/api/emails?limit=1").json()["emails"][0]["runs"]}

    runs = deliver(11, "Invoice 1")
    assert sent == ["A", "B true"]
    assert [runs[k]["status"] for k in "ABC"] == ["completed", "completed", "skipped"]
    assert runs["B"]["log"][0]["type"] == "chain" and runs["B"]["log"][0]["outcome"] == "pass"
    assert "runs only if it stopped by a filter" in runs["C"]["log"][0]["detail"]

    sent.clear()
    runs = deliver(12, "Hello")
    assert sent == ["C"] and runs["B"]["status"] == "skipped" and runs["C"]["status"] == "completed"

    # a paused parent counts as "did not run"
    assert c.put(f"/api/tasks/{a['id']}", json={**a, "enabled": False}).status_code == 200
    sent.clear()
    msg = EmailMessage()
    msg["Subject"] = "Invoice 2"
    msg.set_content("x")
    monkeypatch.setattr(gmail, "fetch_new", lambda acct, v, last, limit: gmail.FetchResult(
        uidvalidity=9, last_uid=last, messages=[(13, msg.as_bytes())]))
    assert poller.poll_integration(gid)["runs"] == 2
    runs = {r["task_name"]: r for r in c.get("/api/emails?limit=1").json()["emails"][0]["runs"]}
    assert not sent and "(paused)" in runs["B"]["log"][0]["detail"]

    # moving A to another inbox moves its chained tasks along
    r = c.put(f"/api/tasks/{a['id']}", json={**a, "enabled": True, "gmail_integration_id": first})
    assert r.status_code == 200 and sorted(r.json()["chain"]["updated"]) == ["B", "C"]
    assert task(cc["id"])["gmail_integration_id"] == first
