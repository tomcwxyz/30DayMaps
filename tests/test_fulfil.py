"""Fulfilment against fake Stripe, Prodigi and file storage. No network."""
import json
from pathlib import Path

import pytest

from maps import fulfil

RECIPE = json.dumps({"v": 1, "lat": 54.97, "lon": -1.61, "name": "Heaton", "title": "Home",
                     "subtitle": "Where we met", "kicker": "", "paper": "A3", "orient": "portrait",
                     "width_km": 3, "theme": "night", "source": "osm"})
SHOP = {"sizes": {"A3": {"price": 3500, "prodigi_sku": "TEST-SKU-A3"}, "A4": {"price": None, "prodigi_sku": None}},
        "fulfilment": {"shipping_method": "Standard"}}
ADDRESS = {"line1": "12 Secret Street", "line2": None, "city": "Newcastle upon Tyne", "state": None,
           "postal_code": "NE6 5XX", "country": "GB"}
PERSONAL = ["Jo Bloggs", "Secret Street", "NE6 5XX", "jo@example.com", "Where we met", "blob.example"]


def session(meta=None, *, paid=True, new_api=False, created=1_000_000, product=None):
    shipping = {"name": "Jo Bloggs", "address": ADDRESS}
    s = {"id": "cs_test_a1b2c3d4e5f6g7h8", "payment_status": "paid" if paid else "unpaid", "created": created,
         "metadata": {"recipe": RECIPE, **({"product": product} if product else {})},
         "customer_details": {"email": "jo@example.com"},
         "payment_intent": {"id": "pi_3Abcdefgh12345678", "metadata": meta or {}}}
    if new_api:
        s["collected_information"] = {"shipping_details": shipping}
    else:
        s["shipping_details"] = shipping
    return s


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class FakeHTTP:
    """Records calls; answers from a list of (method, url fragment, status, body) rules."""
    def __init__(self, rules):
        self.rules, self.calls = rules, []

    def _answer(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for m, frag, status, body in self.rules:
            if m == method and frag in url:
                return Resp(status, body(kw) if callable(body) else body)
        raise AssertionError(f"unexpected {method} {url}")

    def get(self, url, **kw):
        return self._answer("GET", url, **kw)

    def post(self, url, **kw):
        return self._answer("POST", url, **kw)


def fake_render(recipe, out, kinds, min_long_px=None):
    names = {"print": "x-300dpi.png", "web": "x-web.png", "pdf": "x.pdf"}
    files = {k: Path(out) / names[k] for k in kinds}
    for f in files.values():
        f.write_bytes(b"file")
    return files


def uploads():
    log = []
    def up(cmd, *args):
        log.append((cmd, args))
        if cmd == "put":
            return {"pathname": args[1]}
        if cmd == "sign":
            return {"url": f"https://blob.example/{args[0]}?sig={args[1]}h"}
        return {}
    return up, log


def test_prepare_renders_stores_and_records_on_the_payment(capsys):
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session()), ("POST", "/payment_intents/", 200, {})])
    up, log = uploads()
    assert fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=up,
                          renderer=fake_render, shop=SHOP) == "submit"
    assert [(c, a[1] if c == "put" else a[0]) for c, a in log] == [
        ("put", "orders/pi_3Abcdefgh12345678-print.png"), ("put", "orders/pi_3Abcdefgh12345678-preview.png"),
        ("sign", "orders/pi_3Abcdefgh12345678-preview.png")]
    meta = http.calls[-1][2]["data"]
    assert meta["metadata[print_status]"] == "awaiting approval"
    assert meta["metadata[print_file]"] == "orders/pi_3Abcdefgh12345678-print.png"   # private path, not a link
    assert meta["metadata[print_preview"+"]"].startswith("https://blob.example/orders/") and "168h" in meta["metadata[print_preview]"]
    out = capsys.readouterr().out
    assert not any(p in out for p in PERSONAL)


def test_prepare_skips_orders_already_sent():
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session({"prodigi_order": "ord_1"}))])
    assert fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=None, renderer=None, shop=SHOP) == "skip"


def test_prepare_refuses_unpaid_and_bad_ids():
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session(paid=False))])
    with pytest.raises(fulfil.FulfilError, match="isn't paid"):
        fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", shop=SHOP)
    with pytest.raises(fulfil.FulfilError, match="session ID"):
        fulfil.prepare("cs_test_x/../../charges", http=http, key="sk", shop=SHOP)


def test_size_without_a_prodigi_product_stops_before_rendering():
    shop = {"sizes": {"A3": {"price": 3500, "prodigi_sku": None}}}
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session())])
    with pytest.raises(fulfil.FulfilError, match="prodigi_sku"):
        fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", renderer=None, shop=shop)


@pytest.mark.parametrize("new_api", [False, True])
def test_submit_sends_one_idempotent_order_to_prodigi_sandbox(new_api, monkeypatch, capsys):
    monkeypatch.delenv("PRODIGI_ENV", raising=False)
    sent = {}
    def created(kw):
        sent.update(kw)
        return {"outcome": "Created", "order": {"id": "ord_829"}}
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session({"print_file": "orders/f.png"}, new_api=new_api)),
                     ("POST", "api.sandbox.prodigi.com/v4.0/orders", 200, created),
                     ("POST", "/payment_intents/", 200, {})])
    up, _ = uploads()
    assert fulfil.submit("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", prodigi_key="pk", shop=SHOP, uploader=up) == "ord_829"
    body = sent["json"]
    assert sent["headers"] == {"X-API-Key": "pk"}
    assert body["idempotencyKey"] == body["merchantReference"] == "pi_3Abcdefgh12345678"
    assert body["shippingMethod"] == "Standard"
    assert body["recipient"] == {"name": "Jo Bloggs", "email": "jo@example.com", "address": {
        "line1": "12 Secret Street", "postalOrZipCode": "NE6 5XX", "countryCode": "GB", "townOrCity": "Newcastle upon Tyne"}}
    item = body["items"][0]
    assert (item["sku"], item["copies"], item["sizing"]) == ("TEST-SKU-A3", 1, "fillPrintArea")
    assert item["assets"] == [{"printArea": "default", "url": "https://blob.example/orders/f.png?sig=72h"}]   # signed for 3 days
    assert http.calls[-1][2]["data"]["metadata[prodigi_order]"] == "ord_829"
    assert not any(p in capsys.readouterr().out for p in PERSONAL)


def test_submit_goes_live_only_when_told(monkeypatch):
    monkeypatch.setenv("PRODIGI_ENV", "live")
    assert fulfil.prodigi_base() == "https://api.prodigi.com/v4.0"
    monkeypatch.setenv("PRODIGI_ENV", "production")
    with pytest.raises(fulfil.FulfilError):
        fulfil.prodigi_base()


def test_refused_order_is_recorded_privately_and_stops(capsys):
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session({"print_file": "orders/f.png"})),
                     ("POST", "/orders", 400, {"outcome": "ValidationFailed", "failures": {"recipient.address": ["Jo Bloggs NE6 5XX invalid"]}}),
                     ("POST", "/payment_intents/", 200, {})])
    with pytest.raises(fulfil.FulfilError, match="ValidationFailed") as err:
        fulfil.submit("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", prodigi_key="pk", shop=SHOP, uploader=uploads()[0])
    assert not any(p in str(err.value) for p in PERSONAL)
    assert "NE6 5XX" in http.calls[-1][2]["data"]["metadata[print_error]"]  # detail kept in Stripe only


def test_submit_does_nothing_for_an_order_already_sent():
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session({"prodigi_order": "ord_1"}))])
    assert fulfil.submit("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", prodigi_key="pk", shop=SHOP) == "ord_1"
    assert len(http.calls) == 1


def test_incomplete_address_is_refused():
    with pytest.raises(fulfil.FulfilError, match="incomplete"):
        fulfil.recipient({"name": "Jo", "address": {"line1": "1 Road", "country": "GB"}}, None)


def test_status_records_tracking_and_deletes_shipped_files():
    shipped = session({"prodigi_order": "ord_1", "print_file": "orders/pi_3Abcdefgh12345678-print.png",
                       "print_preview": "https://blob.example/p"})
    waiting = session({"print_file": "orders/g.png", "print_status": "awaiting approval"}, created=1_000_000 - 3 * 86400)
    waiting["payment_intent"]["id"] = "pi_waiting000001"
    http = FakeHTTP([("GET", "/checkout/sessions", 200, {"data": [shipped, waiting], "has_more": False}),
                     ("GET", "/orders/ord_1", 200, {"order": {"status": {"stage": "Complete", "issues": []},
                      "shipments": [{"status": "Shipped", "tracking": {"url": "https://track.example/1", "number": "1"}}]}}),
                     ("POST", "/payment_intents/", 200, {})])
    up, log = uploads()
    result = fulfil.status(http=http, key="sk", prodigi_key="pk", uploader=up, shop=SHOP, now=1_000_000 + 3600)
    assert result["counts"]["shipped"] == 1 and result["counts"]["awaiting approval"] == 1
    assert log == [("del", ("orders/pi_3Abcdefgh12345678-print.png", "orders/pi_3Abcdefgh12345678-preview.png"))]
    posted = [c[2]["data"] for c in http.calls if c[0] == "POST"]
    assert posted[0] == {"metadata[print_status]": "shipped", "metadata[tracking]": "https://track.example/1"}
    assert any("over 48 hours" in n for n in result["notes"])  # the waiting order is 3 days old


def test_status_flags_sizes_that_cannot_be_printed():
    shop = {"sizes": {"A2": {"price": 4500, "prodigi_sku": None}}, "fulfilment": {"shipping_method": "Standard"}}
    http = FakeHTTP([("GET", "/checkout/sessions", 200, {"data": [], "has_more": False})])
    assert fulfil.status(http=http, key="sk", shop=shop)["notes"] == ["Size A2 is for sale but has no prodigi_sku"]


def test_cli_never_prints_tracebacks(monkeypatch, capsys):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk")
    def boom(*a, **k):
        raise RuntimeError("https://blob.example/secret Jo Bloggs")
    monkeypatch.setattr(fulfil, "prepare", boom)
    with pytest.raises(SystemExit):
        fulfil.main(["prepare", "--session", "cs_test_a1b2c3d4e5f6g7h8"])
    out = capsys.readouterr()
    assert "RuntimeError" in out.out and "Jo Bloggs" not in out.out + out.err


def test_shop_json_in_repo_is_valid_and_closed():
    shop = fulfil.load_shop()
    assert all("prodigi_sku" in s for s in shop["sizes"].values())
    assert fulfil.shipping_method(shop) == "Standard"


# --- Digital orders ----------------------------------------------------------

def digital_session(meta=None, **kw):
    s = session(meta, product="digital", **kw)
    s.pop("shipping_details", None)  # digital checkouts collect no address
    return s


def test_digital_order_is_rendered_stored_and_emailed(monkeypatch, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("DOWNLOAD_SECRET", "k")
    monkeypatch.setenv("SITE_URL", "https://shop.example/")
    monkeypatch.setenv("SHOP_EMAIL_FROM", "Footprints <prints@example.org>")
    emailed = {}
    def mail(kw):
        emailed.update(kw)
        return {"id": "email_1"}
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, digital_session()),
                     ("POST", "api.resend.com/emails", 200, mail),
                     ("POST", "/payment_intents/", 200, {})])
    up, log = uploads()
    shop = dict(SHOP, digital={"price": 500, "link_days": 30})
    assert fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=up,
                          renderer=fake_render, shop=shop) == "skip"   # no approval or Prodigi step
    assert [a[1] for _, a in log] == ["digital/pi_3Abcdefgh12345678-print.png", "digital/pi_3Abcdefgh12345678-print.pdf"]
    body = emailed["json"]
    assert body["to"] == ["jo@example.com"] and body["from"] == "Footprints <prints@example.org>"
    assert "Home" in body["subject"]
    assert "https://shop.example/api/download?f=digital%2Fpi_3Abcdefgh12345678-print.png&amp;x=" in body["html"] \
        or "https://shop.example/api/download?f=digital%2Fpi_3Abcdefgh12345678-print.png&x=" in body["html"]
    assert "print.pdf" in body["text"] and "&s=" in body["text"]
    stored = [c[2]["data"] for c in http.calls if c[0] == "POST" and "payment_intents" in c[1]]
    assert any(m.get("metadata[digital_png]") == "digital/pi_3Abcdefgh12345678-print.png" for m in stored)   # paths, not links
    assert "30 days" in body["text"]
    assert emailed["headers"]["Idempotency-Key"] == "digital-pi_3Abcdefgh12345678"
    final = http.calls[-1][2]["data"]
    assert final["metadata[print_status]"] == "emailed" and final["metadata[digital_sent]"]
    assert not any(p in capsys.readouterr().out for p in PERSONAL + ["Home"])
    assert not any("prodigi" in c[1] for c in http.calls)


def test_digital_order_already_emailed_is_left_alone():
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, digital_session({"digital_sent": "2026-11-04T10:00:00Z"}))])
    assert fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=None, renderer=None, shop=SHOP) == "skip"
    assert len(http.calls) == 1


def test_digital_retry_after_failed_email_reuses_files(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("DOWNLOAD_SECRET", "k")
    monkeypatch.setenv("SITE_URL", "https://shop.example")
    monkeypatch.setenv("SHOP_EMAIL_FROM", "prints@example.org")
    meta = {"digital_png": "digital/a.png", "digital_pdf": "digital/a.pdf"}
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, digital_session(meta)),
                     ("POST", "api.resend.com/emails", 200, {"id": "e"}), ("POST", "/payment_intents/", 200, {})])
    def no_render(*a):
        raise AssertionError("should not re-render")
    fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=None, renderer=no_render, shop=SHOP)


def test_digital_without_email_setup_stops_clearly(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("DOWNLOAD_SECRET", "k")
    monkeypatch.setenv("SITE_URL", "https://shop.example")
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, digital_session()), ("POST", "/payment_intents/", 200, {})])
    up, _ = uploads()
    with pytest.raises(fulfil.FulfilError, match="Email isn't set up"):
        fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=up, renderer=fake_render, shop=SHOP)


def test_digital_orders_never_go_to_prodigi():
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, digital_session())])
    with pytest.raises(fulfil.FulfilError, match="Digital"):
        fulfil.submit("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", prodigi_key="pk", shop=SHOP)


def test_status_expires_digital_links_after_the_promised_days():
    old = digital_session({"digital_sent": "x", "digital_png": "digital/a.png", "digital_pdf": "digital/a.pdf"},
                          created=1_000_000 - 31 * 86400)
    fresh = digital_session({"digital_sent": "x", "digital_png": "digital/c.png", "digital_pdf": "digital/c.pdf"})
    fresh["payment_intent"]["id"] = "pi_fresh0000000001"
    stuck = digital_session(created=1_000_000 - 5 * 3600)
    stuck["payment_intent"]["id"] = "pi_stuck0000000001"
    http = FakeHTTP([("GET", "/checkout/sessions", 200, {"data": [old, fresh, stuck], "has_more": False}),
                     ("POST", "/payment_intents/", 200, {})])
    up, log = uploads()
    shop = dict(SHOP, digital={"price": 500, "link_days": 30})
    result = fulfil.status(http=http, key="sk", uploader=up, shop=shop, now=1_000_000)
    assert log == [("del", ("digital/a.png", "digital/a.pdf"))]
    assert result["counts"]["digital emailed"] == 2 and result["counts"]["needs attention"] == 1


def test_digital_png_is_at_least_a2_resolution(monkeypatch, tmp_path):
    from maps import prints
    seen = {}
    def fake_make(spec, out):
        seen["dpi"] = spec.dpi
        files = []
        for name in (f"x-{spec.dpi}dpi.png", "x.pdf"):
            (tmp_path / name).write_bytes(b"f"); files.append(str(tmp_path / name))
        return {"files": files}
    monkeypatch.setattr(prints, "make", fake_make)
    a4 = json.dumps({**json.loads(RECIPE), "paper": "A4"})
    fulfil.render(a4, tmp_path, ("print", "pdf"), fulfil.DIGITAL_MIN_LONG_PX)
    assert seen["dpi"] == 601 and 297 / 25.4 * seen["dpi"] >= 7016   # A4 rendered finer
    a1 = json.dumps({**json.loads(RECIPE), "paper": "A1"})
    fulfil.render(a1, tmp_path, ("print", "pdf"), fulfil.DIGITAL_MIN_LONG_PX)
    assert seen["dpi"] == 300                                         # big sizes keep 300 dpi


def test_download_links_match_the_shop_server():
    """Same signature the Node /api/download checks (see web/footprints/test/download.test.js)."""
    import os
    os.environ.update(DOWNLOAD_SECRET="k", SITE_URL="https://shop.example/")
    link = fulfil.download_link("digital/pi_1-print.png", 30, now=1700000000 - 30 * 86400)
    assert link == ("https://shop.example/api/download?f=digital%2Fpi_1-print.png&x=1700000000"
                    "&s=oHmjMTwLso0H9eIenufXhz0F-pXfGGhDgUG-pxljm2s")


def test_digital_without_download_setup_stops_clearly(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_SECRET", raising=False)
    with pytest.raises(fulfil.FulfilError, match="DOWNLOAD_SECRET"):
        fulfil.download_link("digital/x.png", 30)


# --- Customer updates for prints ---------------------------------------------

def _mail_env(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("SHOP_EMAIL_FROM", "Footprints <prints@example.org>")


def test_print_order_gets_a_confirmation_email_once(monkeypatch, capsys):
    _mail_env(monkeypatch)
    sent = []
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session()),
                     ("POST", "api.resend.com/emails", 200, lambda kw: sent.append(kw) or {"id": "e"}),
                     ("POST", "/payment_intents/", 200, {})])
    up, _ = uploads()
    assert fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=up,
                          renderer=fake_render, shop=SHOP) == "submit"
    assert len(sent) == 1 and sent[0]["json"]["to"] == ["jo@example.com"]
    assert sent[0]["json"]["subject"].startswith("Thanks for your order")
    assert sent[0]["json"]["text"].startswith("Hi Jo,") and "\nTom\n" in sent[0]["json"]["text"]
    assert sent[0]["headers"]["Idempotency-Key"] == "email_received-pi_3Abcdefgh12345678"
    flags = [c[2]["data"] for c in http.calls if c[0] == "POST" and "payment_intents" in c[1]]
    assert any("metadata[email_received]" in f for f in flags)
    assert not any(p in capsys.readouterr().out for p in PERSONAL)

    # a re-run (e.g. after approval was retried) doesn't email again
    sent.clear()
    http2 = FakeHTTP([("GET", "/checkout/sessions/", 200, session({"email_received": "x", "print_file": "orders/f.png"}))])
    fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http2, key="sk", uploader=up, renderer=fake_render, shop=SHOP)
    assert sent == []


def test_a_failed_confirmation_never_holds_up_the_print(monkeypatch):
    _mail_env(monkeypatch)
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session()),
                     ("POST", "api.resend.com/emails", 500, {}),
                     ("POST", "/payment_intents/", 200, {})])
    up, _ = uploads()
    assert fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=up,
                          renderer=fake_render, shop=SHOP) == "submit"


def test_shipping_sends_the_tracking_link_once(monkeypatch):
    _mail_env(monkeypatch)
    sent = []
    shipped = session({"prodigi_order": "ord_1", "print_file": "orders/pi_3Abcdefgh12345678-print.png"})
    shipped["customer_details"] = {"email": "jo@example.com"}
    http = FakeHTTP([("GET", "/checkout/sessions", 200, {"data": [shipped], "has_more": False}),
                     ("GET", "/orders/ord_1", 200, {"order": {"status": {"stage": "Complete", "issues": []},
                      "shipments": [{"status": "Shipped", "tracking": {"url": "https://track.example/1", "number": "1"}}]}}),
                     ("POST", "api.resend.com/emails", 200, lambda kw: sent.append(kw) or {"id": "e"}),
                     ("POST", "/payment_intents/", 200, {})])
    up, _ = uploads()
    fulfil.status(http=http, key="sk", prodigi_key="pk", uploader=up, shop=SHOP, now=1_000_000 + 3600)
    assert len(sent) == 1 and "https://track.example/1" in sent[0]["json"]["text"]
    assert sent[0]["json"]["subject"].startswith("Your print is on its way")
    assert sent[0]["json"]["text"].startswith("Hi Jo,")


def test_first_names_are_used_only_when_sensible():
    assert fulfil.first_name("Jo Bloggs") == "Jo"
    assert fulfil.first_name("") == "" and fulfil.first_name(None) == "" and fulfil.first_name("123") == ""
    subject, text, html = fulfil.received_email("Home <b>", "A3 print", "", {"email": {"signoff": "Sam"}})
    assert text.startswith("Hello,") and "\nSam\n" in text and "<b>" not in html


def test_owner_gets_a_preview_to_approve(monkeypatch, capsys):
    _mail_env(monkeypatch)
    monkeypatch.setenv("SHOP_OWNER_EMAIL", "owner@example.org")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    sent = []
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, session()),
                     ("POST", "api.resend.com/emails", 200, lambda kw: sent.append(kw) or {"id": "e"}),
                     ("POST", "/payment_intents/", 200, {})])
    up, _ = uploads()
    fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk_test_x", uploader=up, renderer=fake_render, shop=SHOP)
    owner = [m for m in sent if m["json"]["to"] == ["owner@example.org"]]
    assert len(owner) == 1
    body = owner[0]["json"]
    assert body["subject"].startswith("Approve this print?")
    assert '<img src="https://blob.example/orders/pi_3Abcdefgh12345678-preview.png' in body["html"]
    assert "https://github.com/o/r/actions/runs/42" in body["html"]
    assert "dashboard.stripe.com/test/payments/pi_3Abcdefgh12345678" in body["text"]
    assert not any(p in capsys.readouterr().out for p in PERSONAL)   # nothing personal in the public log


# --- Peaks orders --------------------------------------------------------------

PEAKS_RECIPE = json.dumps({"v": 1, "place": "", "lat": 54.53, "lon": -2.99, "name": "Helvellyn by Striding Edge",
                           "region": "", "style": "poster", "theme": "paper", "labels": 1, "details": 1,
                           "title": "Our round", "subtitle": "18 October 2026", "paper": "A3", "orient": "portrait",
                           "width": 8, "detail": 90, "rows": 64, "seen": "S", "dist": 10, "facing": 0, "fov": 160,
                           "reach": 35, "route": 3})
ROUTE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"   # three points, split across two metadata values below


def peaks_session(meta=None, product=None, **kw):
    s = session(meta, product=product, **kw)
    s["metadata"] = {"recipe": PEAKS_RECIPE, "shop": "peaks", "route_0": ROUTE[:10], "route_1": ROUTE[10:],
                     **({"product": product} if product else {})}
    if product == "digital":
        s.pop("shipping_details", None)
    return s


def test_orders_say_which_shop_they_are_from():
    assert fulfil.order_from_session(session()).shop == "footprints"   # older orders carry no shop
    o = fulfil.order_from_session(peaks_session())
    assert o.shop == "peaks" and o.route == ROUTE
    bad = peaks_session(); bad["metadata"]["shop"] = "elsewhere"
    with pytest.raises(fulfil.FulfilError, match="Unknown shop"):
        fulfil.order_from_session(bad)


def test_peaks_print_is_rendered_with_its_route_and_sent_with_its_own_reference(monkeypatch):
    seen = {}
    def peaks_render(recipe, out, kinds, min_long_px=None, route=None):
        seen.update(recipe=recipe, route=route, kinds=kinds)
        return fake_render(recipe, out, kinds)
    monkeypatch.setitem(fulfil.RENDERERS, "peaks", peaks_render)
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, peaks_session()), ("POST", "/payment_intents/", 200, {})])
    up, _ = uploads()
    assert fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=up, shop=SHOP) == "submit"
    assert seen["route"] == ROUTE and json.loads(seen["recipe"])["style"] == "poster"
    payload = fulfil.order_payload(fulfil.order_from_session(peaks_session()), "SKU", "Standard", "https://f")
    assert payload["items"][0]["merchantReference"] == "peaks-print"


def test_peaks_digital_email_uses_its_own_words_and_site(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("DOWNLOAD_SECRET", "k")
    monkeypatch.setenv("SITE_URL", "https://footprints.example")   # the workflow's default site
    monkeypatch.setenv("SHOP_EMAIL_FROM", "Tom <prints@example.org>")
    emailed = {}
    http = FakeHTTP([("GET", "/checkout/sessions/", 200, peaks_session(product="digital")),
                     ("POST", "api.resend.com/emails", 200, lambda kw: emailed.update(kw) or {"id": "e"}),
                     ("POST", "/payment_intents/", 200, {})])
    up, _ = uploads()
    shop = fulfil.load_shop(fulfil.SHOP_FILES["peaks"])
    monkeypatch.setitem(fulfil.RENDERERS, "peaks", lambda r, out, kinds, min_long_px=None, route=None: fake_render(r, out, kinds))
    assert fulfil.prepare("cs_test_a1b2c3d4e5f6g7h8", http=http, key="sk", uploader=up, shop=shop) == "skip"
    body = emailed["json"]
    assert "peaks print" in body["text"] and "open elevation data" in body["text"]
    assert "every building" not in body["text"] and "Peaks · peaks.tomcw.xyz" in body["text"]
    assert "https://peaks.tomcw.xyz/api/download?" in body["text"] and "footprints.example" not in body["text"]
    assert body["subject"] == "Your print of Our round is ready"
    assert body["from"] == "Peaks <prints@example.org>"   # shop's own name, shared address


def test_footprints_emails_are_unchanged():
    subject, text, _ = fulfil.digital_email("Home", "p", "d", 30, "Jo", {"email": {"signoff": "Tom"}})
    assert subject == "Your map of Home is ready" and "footprints map" in text and "every building in OpenStreetMap" in text


def test_owner_approval_email_describes_a_peaks_order():
    subject, text, _ = fulfil.approval_email(json.loads(PEAKS_RECIPE), "A3 print", "https://p", "https://run", "https://s", "peaks")
    assert "Shop: Peaks" in text and "Style: poster" in text and "Route: yes, 3 points" in text


def test_status_checks_each_order_against_its_own_shop():
    up, _ = uploads()
    http = FakeHTTP([("GET", "/checkout/sessions", 200, {"data": [
        session({"print_file": "orders/a.png"}, created=1_000_000),
        peaks_session(product="digital", meta={"digital_sent": "x", "digital_png": "d/a", "digital_pdf": "d/b"}, created=1_000_000)],
        "has_more": False})])
    result = fulfil.status(http=http, key="sk", uploader=up, now=1_000_000 + 3600)
    assert result["counts"]["awaiting approval"] == 1 and result["counts"]["digital emailed"] == 1


def test_peaks_shop_json_is_valid_and_sells_both_panoramas():
    shop = fulfil.load_shop(fulfil.SHOP_FILES["peaks"])
    assert fulfil.config_problems(shop) == []
    assert shop["site"] == "https://peaks.tomcw.xyz"
    assert set(p for p in shop["sizes"] if p.startswith("pano")) == {"pano75", "pano90"}
    assert fulfil.sku_for(shop, "pano75") == "GLOBAL-FAP-10X30" and fulfil.sku_for(shop, "pano90") == "GLOBAL-FAP-12X36"
    assert shop["sizes"]["A3"]["prodigi_sku"] == fulfil.load_shop()["sizes"]["A3"]["prodigi_sku"]


def test_download_secret_per_shop(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_SECRET", "shared")
    monkeypatch.delenv("PEAKS_DOWNLOAD_SECRET", raising=False)
    assert fulfil.download_secret("peaks") == "shared"
    monkeypatch.setenv("PEAKS_DOWNLOAD_SECRET", "peaks-only")
    assert fulfil.download_secret("peaks") == "peaks-only"
    assert fulfil.download_secret("footprints") == "shared"
    a = fulfil.download_link("digital/x.png", 30, now=1700000000, site="https://p.example", shop_name="peaks")
    b = fulfil.download_link("digital/x.png", 30, now=1700000000, site="https://p.example")
    assert a != b


def test_render_tries_again_before_giving_up(monkeypatch):
    monkeypatch.setattr(fulfil, "RENDER_WAIT", 0)
    calls = []
    def flaky(recipe, out, kinds):
        calls.append(1)
        if len(calls) < 3: raise RuntimeError("slow")
        return {"web": out}
    order = fulfil.Order(session_id="cs_x", pi_id="pi_123", metadata={}, recipe="{}", shipping={}, email=None, created=0)
    assert fulfil._render(flaky, order, Path("."), ("web",)) == {"web": Path(".")}
    assert len(calls) == 3
    calls.clear()
    def broken(recipe, out, kinds): calls.append(1); raise RuntimeError("down")
    with pytest.raises(RuntimeError): fulfil._render(broken, order, Path("."), ("web",))
    assert len(calls) == fulfil.RENDER_ATTEMPTS
