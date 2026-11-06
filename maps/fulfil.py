"""Turn paid footprints shop orders into Prodigi print orders.

    python -m maps.fulfil prepare --session cs_...   render the print and store the file
                                                    (digital orders: render, store and email)
    python -m maps.fulfil submit  --session cs_...   send the order to Prodigi
    python -m maps.fulfil status                     check recent orders, tidy up shipped files

The "Print order" GitHub workflow runs prepare, waits for approval, then runs submit.
Digital orders finish in prepare: the files are emailed to the customer as download links.
Stripe is the record: each order's progress is kept in its payment's metadata
(print_status, print_preview, print_file, prodigi_order, tracking, print_error;
digital_png, digital_pdf, digital_sent for digital orders).

Files live in a private Vercel Blob store under orders/ and digital/. Prodigi and the
preview get time-limited signed links; digital-order emails link to the shop's
/api/download, which checks a signature made with DOWNLOAD_SECRET before handing out
a fresh download link, so email links can last as long as promised.

This repository is public, so its Actions logs are too. Nothing here prints a
customer's name, address, email, map title or file URL; logs name orders only by the
last characters of the Stripe payment ID. Detail goes in the payment's metadata instead.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SHOP_JSON = ROOT / "web" / "footprints" / "shop.json"
BLOB_SCRIPT = ROOT / "web" / "footprints" / "scripts" / "blob.mjs"
STRIPE = os.environ.get("STRIPE_API_BASE", "https://api.stripe.com") + "/v1"
PRODIGI = {"sandbox": "https://api.sandbox.prodigi.com/v4.0", "live": "https://api.prodigi.com/v4.0"}
SHIPPING_METHODS = {"Budget", "Standard", "StandardPlus", "Express", "Overnight"}
SESSION_ID = re.compile(r"^cs_(test|live)_[A-Za-z0-9]{10,200}$")
APPROVAL_GRACE_HOURS = 48
RESEND = os.environ.get("RESEND_API_BASE", "https://api.resend.com")


class FulfilError(Exception):
    """A problem whose message is safe for public logs (no personal data)."""


# --- Small API helpers -------------------------------------------------------

def _check(r, what):
    if r.status_code >= 400:
        raise FulfilError(f"{what} failed (HTTP {r.status_code})")
    return r.json()


def stripe_get(http, key, path, params=None):
    return _check(http.get(f"{STRIPE}{path}", params=params, auth=(key, ""), timeout=60), "Stripe lookup")


def stripe_set_metadata(http, key, payment_intent: str, values: dict):
    data = {f"metadata[{k}]": ("" if v is None else str(v)[:500]) for k, v in values.items()}
    return _check(http.post(f"{STRIPE}/payment_intents/{payment_intent}", data=data, auth=(key, ""), timeout=60),
                  "Saving order progress to Stripe")


def prodigi_base() -> str:
    env = os.environ.get("PRODIGI_ENV", "sandbox").strip().lower() or "sandbox"
    if env not in PRODIGI:
        raise FulfilError("PRODIGI_ENV must be 'sandbox' or 'live'")
    return PRODIGI[env]


def ref(pi_id: str) -> str:
    return f"order …{pi_id[-8:]}"


# --- Shop settings -----------------------------------------------------------

def load_shop(path: Path = SHOP_JSON) -> dict:
    return json.loads(Path(path).read_text())


def sku_for(shop: dict, paper: str) -> str:
    size = shop.get("sizes", {}).get(paper) or {}
    sku = size.get("prodigi_sku")
    if not sku:
        raise FulfilError(f"No prodigi_sku set for size {paper} in shop.json")
    return sku


def shipping_method(shop: dict) -> str:
    method = (shop.get("fulfilment") or {}).get("shipping_method", "Standard")
    if method not in SHIPPING_METHODS:
        raise FulfilError(f"Unknown Prodigi shipping method {method!r} in shop.json")
    return method


def config_problems(shop: dict) -> list[str]:
    """Sizes on sale that couldn't be printed automatically."""
    problems = []
    for paper, size in shop.get("sizes", {}).items():
        if size.get("price") and not size.get("prodigi_sku"):
            problems.append(f"Size {paper} is for sale but has no prodigi_sku")
    try:
        shipping_method(shop)
    except FulfilError as e:
        problems.append(str(e))
    return problems


# --- Orders ------------------------------------------------------------------

@dataclass
class Order:
    session_id: str
    pi_id: str
    metadata: dict
    recipe: str
    shipping: dict
    email: str | None
    created: int
    product: str = "print"


def load_order(http, key: str, session_id: str) -> Order:
    if not SESSION_ID.match(session_id or ""):
        raise FulfilError("That isn't a Stripe Checkout session ID (cs_…)")
    s = stripe_get(http, key, f"/checkout/sessions/{session_id}", params={"expand[]": "payment_intent"})
    return order_from_session(s)


def order_from_session(s: dict) -> Order:
    if s.get("payment_status") != "paid":
        raise FulfilError("This order isn't paid")
    recipe = (s.get("metadata") or {}).get("recipe")
    if not recipe:
        raise FulfilError("This payment isn't a footprints shop order")
    pi = s.get("payment_intent")
    if not isinstance(pi, dict) or not pi.get("id"):
        raise FulfilError("Stripe didn't return the payment for this order")
    product = (s.get("metadata") or {}).get("product") or "print"
    if product not in ("print", "digital"):
        raise FulfilError("Unknown product on this order")
    email = (s.get("customer_details") or {}).get("email")
    # Older Stripe API versions put the address at shipping_details; newer ones under collected_information.
    shipping = s.get("shipping_details") or (s.get("collected_information") or {}).get("shipping_details")
    if product == "print" and (not shipping or not shipping.get("address")):
        raise FulfilError("This order has no delivery address")
    if product == "digital" and not email:
        raise FulfilError("This order has no email address")
    return Order(session_id=s["id"], pi_id=pi["id"], metadata=pi.get("metadata") or {}, recipe=recipe,
                 shipping=shipping or {}, email=email, created=int(s.get("created") or 0), product=product)


def recipient(shipping: dict, email: str | None) -> dict:
    a = shipping["address"]
    address = {"line1": a.get("line1"), "line2": a.get("line2"), "postalOrZipCode": a.get("postal_code"),
               "countryCode": a.get("country"), "townOrCity": a.get("city"), "stateOrCounty": a.get("state")}
    address = {k: v for k, v in address.items() if v}
    missing = [k for k in ("line1", "postalOrZipCode", "countryCode", "townOrCity") if k not in address]
    if missing or not shipping.get("name"):
        raise FulfilError("The delivery address is incomplete")
    r = {"name": shipping["name"], "address": address}
    if email:
        r["email"] = email
    return r


def order_payload(order: Order, sku: str, method: str, file_url: str) -> dict:
    return {
        "merchantReference": order.pi_id,
        "idempotencyKey": order.pi_id,   # Prodigi won't create a second order for the same payment
        "shippingMethod": method,
        "recipient": recipient(order.shipping, order.email),
        "items": [{
            "merchantReference": "footprints-print",
            "sku": sku,
            "copies": 1,
            "sizing": "fillPrintArea",
            "assets": [{"printArea": "default", "url": file_url}],
        }],
    }


# --- Files -------------------------------------------------------------------

def blob(*args: str) -> dict:
    """Run the Vercel Blob helper (put / sign / del); never echoes its output, which may contain links."""
    done = subprocess.run(["node", str(BLOB_SCRIPT), *args], capture_output=True, text=True, timeout=600)
    if done.returncode != 0:
        raise FulfilError("Storing the print file failed (check BLOB_READ_WRITE_TOKEN)")
    return json.loads(done.stdout or "{}")


DIGITAL_MIN_LONG_PX = 7016  # A2 at 300 dpi: digital files stay sharp printed up to A2, whatever size was chosen


def render(recipe: str, out: Path, kinds=("print", "web"), min_long_px: int | None = None) -> dict[str, Path]:
    """Render the recipe. Returns {"print": PNG, "web": preview PNG, "pdf": vector PDF}.

    The PNG is 300 dpi at the chosen paper size, or finer if min_long_px asks for more pixels.
    """
    from maps import prints
    spec = prints.spec_from_recipe(recipe)
    dpi = 300
    if min_long_px:
        long_in = max(prints.paper_mm(spec.paper, spec.landscape)) / prints.MM_PER_INCH
        dpi = max(dpi, int(-(-min_long_px // long_in)))
    spec.dpi, spec.formats = dpi, list(kinds)
    files = [Path(f) for f in prints.make(spec, out)["files"]]
    found = {"print": [f for f in files if f.name.endswith("dpi.png")],
             "web": [f for f in files if f.name.endswith("-web.png")],
             "pdf": [f for f in files if f.suffix == ".pdf"]}
    return {k: found[k][0] for k in kinds}


PREVIEW_HOURS = 7 * 24   # signed preview link saved on the payment for checking before approval
PRODIGI_HOURS = 72        # signed print-file link given to Prodigi when the order is sent


def signed_url(uploader, pathname: str, hours: int) -> str:
    """Time-limited link to a private file; falls back to a day if the store refuses longer."""
    try:
        return uploader("sign", pathname, str(hours))["url"]
    except FulfilError:
        if hours <= 24:
            raise
        return uploader("sign", pathname, "24")["url"]


def download_link(pathname: str, days: int, now: float | None = None) -> str:
    """A link to /api/download for a digital file, signed to expire after `days`."""
    secret, site = os.environ.get("DOWNLOAD_SECRET"), os.environ.get("SITE_URL", "").rstrip("/")
    if not secret or not site:
        raise FulfilError("Digital downloads aren't set up (DOWNLOAD_SECRET and SITE_URL)")
    expiry = int((now or time.time()) + days * 86400)
    sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{pathname}|{expiry}".encode(),
                                            hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{site}/api/download?" + requests.models.RequestEncodingMixin._encode_params(
        {"f": pathname, "x": expiry, "s": sig})


# --- Email ----------------------------------------------------------------------

def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def digital_email(title: str, png_url: str, pdf_url: str, days: int) -> tuple[str, str, str]:
    subject = f"Your footprints print: {title}"[:150]
    text = (f"Thanks for your order. Here's your print, \"{title}\".\n\n"
            f"High-resolution PNG, sharp printed up to A2, for printing or screens:\n{png_url}\n\n"
            f"PDF, which prints sharp at any size:\n{pdf_url}\n\n"
            f"These links work for {days} days, so save the files somewhere safe.\n\n"
            "The file is for your own use. Please keep the map data credit on it if you print or share it.\n\n"
            "Any problem? Just reply to this email.")
    html = (f"<p>Thanks for your order. Here's your print, <strong>{_esc(title)}</strong>.</p>"
            f'<p><a href="{_esc(png_url)}">Download the high-resolution PNG</a>, sharp printed up to A2, for printing or screens.</p>'
            f'<p><a href="{_esc(pdf_url)}">Download the PDF</a>, which prints sharp at any size.</p>'
            f"<p>These links work for {days} days, so save the files somewhere safe.</p>"
            "<p>The file is for your own use. Please keep the map data credit on it if you print or share it.</p>"
            "<p>Any problem? Just reply to this email.</p>")
    return subject, text, html


def _paper_label(recipe: dict, shop: dict) -> str:
    size = (shop.get("sizes") or {}).get(recipe.get("paper")) or {}
    return size.get("label") or f"{recipe.get('paper', '')} print"


def received_email(title: str, paper: str) -> tuple[str, str, str]:
    subject = f"Order received: {title}"[:150]
    text = (f"Thanks for your order. We've got it: \"{title}\", {paper}.\n\n"
            "Every print is made to order. We check each one before it goes to the printer, "
            "then it's printed and posted, usually reaching you within a week.\n\n"
            "We'll email you again with a tracking link when it's on its way.\n\n"
            "Any problem? Just reply to this email.")
    html = (f"<p>Thanks for your order. We've got it: <strong>{_esc(title)}</strong>, {_esc(paper)}.</p>"
            "<p>Every print is made to order. We check each one before it goes to the printer, "
            "then it's printed and posted, usually reaching you within a week.</p>"
            "<p>We'll email you again with a tracking link when it's on its way.</p>"
            "<p>Any problem? Just reply to this email.</p>")
    return subject, text, html


def shipped_email(title: str, tracking: str) -> tuple[str, str, str]:
    subject = f"On its way: {title}"[:150]
    text = (f"Good news: your print, \"{title}\", has been posted.\n\n"
            f"Track it here:\n{tracking}\n\n"
            "Any problem when it arrives? Just reply to this email.")
    html = (f"<p>Good news: your print, <strong>{_esc(title)}</strong>, has been posted.</p>"
            f'<p><a href="{_esc(tracking)}">Track your parcel</a></p>'
            "<p>Any problem when it arrives? Just reply to this email.</p>")
    return subject, text, html


def notify(http, key: str, pid: str, to: str | None, flag: str, message: tuple[str, str, str]) -> bool:
    """Send an order update once, noting it on the payment. A failed update never holds up the order."""
    if not to:
        return False
    try:
        send_email(http, to, *message, idempotency=f"{flag}-{pid}")
    except FulfilError as e:
        print(f"{ref(pid)}: customer update not sent ({e})")
        return False
    stripe_set_metadata(http, key, pid, {flag: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return True


def send_email(http, to: str, subject: str, text: str, html: str, idempotency: str):
    key, sender = os.environ.get("RESEND_API_KEY"), os.environ.get("SHOP_EMAIL_FROM")
    if not key or not sender:
        raise FulfilError("Email isn't set up (RESEND_API_KEY and SHOP_EMAIL_FROM)")
    body = {"from": sender, "to": [to], "subject": subject, "text": text, "html": html}
    if os.environ.get("SHOP_REPLY_TO"):
        body["reply_to"] = os.environ["SHOP_REPLY_TO"]
    r = http.post(f"{RESEND}/emails", json=body, timeout=60,
                  headers={"Authorization": f"Bearer {key}", "Idempotency-Key": idempotency})
    if r.status_code >= 400:
        raise FulfilError(f"Sending the email failed (HTTP {r.status_code})")


# --- Steps -------------------------------------------------------------------

def prepare(session_id: str, *, http=requests, key=None, uploader=blob, renderer=render, shop=None) -> str:
    """Render and store the print. Returns 'submit', or 'skip' when nothing more is needed."""
    key = key or os.environ["STRIPE_SECRET_KEY"]
    order = load_order(http, key, session_id)
    shop = shop or load_shop()
    if order.product == "digital":
        return deliver_digital(order, http=http, key=key, uploader=uploader, renderer=renderer, shop=shop)
    if order.metadata.get("prodigi_order"):
        print(f"{ref(order.pi_id)}: already sent to print; nothing to do")
        return "skip"
    from maps import prints
    sku_for(shop, prints.spec_from_recipe(order.recipe).paper)  # fail early if the size can't be printed
    if not order.metadata.get("email_received"):
        recipe = json.loads(order.recipe)
        if notify(http, key, order.pi_id, order.email, "email_received",
                  received_email(recipe.get("title") or "your map", _paper_label(recipe, shop))):
            print(f"{ref(order.pi_id)}: order confirmation emailed")
    if order.metadata.get("print_file"):
        print(f"{ref(order.pi_id)}: print file already made; waiting for approval")
        return "submit"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            files = renderer(order.recipe, Path(tmp), ("print", "web"))
            print_path = uploader("put", str(files["print"]), f"orders/{order.pi_id}-print.png")["pathname"]
            preview_path = uploader("put", str(files["web"]), f"orders/{order.pi_id}-preview.png")["pathname"]
            preview_url = signed_url(uploader, preview_path, PREVIEW_HOURS)
    except FulfilError:
        raise
    except Exception as e:  # keep tracebacks (which can contain URLs) out of public logs
        raise FulfilError(f"Rendering the print failed ({type(e).__name__})") from None
    stripe_set_metadata(http, key, order.pi_id, {
        "print_status": "awaiting approval", "print_file": print_path, "print_preview": preview_url, "print_error": ""})
    print(f"{ref(order.pi_id)}: print rendered and stored; preview link saved on the payment in Stripe")
    return "submit"


def deliver_digital(order: Order, *, http, key, uploader, renderer, shop) -> str:
    """Render the PNG and PDF, store them, and email the customer download links."""
    if order.metadata.get("digital_sent"):
        print(f"{ref(order.pi_id)}: digital file already emailed; nothing to do")
        return "skip"
    days = int((shop.get("digital") or {}).get("link_days") or 30)
    try:
        png_path, pdf_path = order.metadata.get("digital_png"), order.metadata.get("digital_pdf")
        if not (png_path and pdf_path):  # a retry after a failed email reuses the stored files
            with tempfile.TemporaryDirectory() as tmp:
                files = renderer(order.recipe, Path(tmp), ("print", "pdf"), DIGITAL_MIN_LONG_PX)
                png_path = uploader("put", str(files["print"]), f"digital/{order.pi_id}-print.png")["pathname"]
                pdf_path = uploader("put", str(files["pdf"]), f"digital/{order.pi_id}-print.pdf")["pathname"]
            stripe_set_metadata(http, key, order.pi_id, {"print_status": "file made, emailing",
                                                         "digital_png": png_path, "digital_pdf": pdf_path})
    except FulfilError:
        raise
    except Exception as e:
        raise FulfilError(f"Rendering the digital file failed ({type(e).__name__})") from None
    title = json.loads(order.recipe).get("title") or "your map"
    png_url, pdf_url = download_link(png_path, days), download_link(pdf_path, days)
    send_email(http, order.email, *digital_email(title, png_url, pdf_url, days), idempotency=f"digital-{order.pi_id}")
    stripe_set_metadata(http, key, order.pi_id, {"print_status": "emailed", "print_error": "",
                                                 "digital_sent": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    print(f"{ref(order.pi_id)}: digital file emailed")
    return "skip"


def submit(session_id: str, *, http=requests, key=None, prodigi_key=None, shop=None, uploader=blob) -> str | None:
    key = key or os.environ["STRIPE_SECRET_KEY"]
    prodigi_key = prodigi_key or os.environ["PRODIGI_API_KEY"]
    order = load_order(http, key, session_id)
    if order.product != "print":
        raise FulfilError("Digital orders aren't sent to Prodigi")
    if order.metadata.get("prodigi_order"):
        print(f"{ref(order.pi_id)}: already sent to print; nothing to do")
        return order.metadata["prodigi_order"]
    print_path = order.metadata.get("print_file")
    if not print_path:
        raise FulfilError("No print file yet; run the prepare step first")
    file_url = signed_url(uploader, print_path, PRODIGI_HOURS)
    shop = shop or load_shop()
    from maps import prints
    payload = order_payload(order, sku_for(shop, prints.spec_from_recipe(order.recipe).paper),
                            shipping_method(shop), file_url)
    r = http.post(f"{prodigi_base()}/orders", json=payload, headers={"X-API-Key": prodigi_key}, timeout=120)
    body = {}
    try:
        body = r.json()
    except ValueError:
        pass
    prodigi_id = (body.get("order") or {}).get("id")
    if r.status_code >= 400 or not prodigi_id:
        outcome = body.get("outcome") or "no outcome given"
        detail = json.dumps({"status": r.status_code, "outcome": outcome,
                             "failures": body.get("failures") or body.get("errors")})[:500]
        stripe_set_metadata(http, key, order.pi_id, {"print_status": "Prodigi refused the order", "print_error": detail})
        raise FulfilError(f"Prodigi refused the order (HTTP {r.status_code}, {outcome}); details saved on the payment in Stripe")
    stripe_set_metadata(http, key, order.pi_id, {"prodigi_order": prodigi_id, "print_status": "sent to print",
                                                 "print_error": ""})
    print(f"{ref(order.pi_id)}: sent to Prodigi ({body.get('outcome', 'created')})")
    return prodigi_id


def status(*, http=requests, key=None, prodigi_key=None, uploader=blob, shop=None, now=None,
           days: int = 45) -> dict:
    """Check recent orders. Records tracking on the payment and deletes shipped print files."""
    key = key or os.environ["STRIPE_SECRET_KEY"]
    prodigi_key = prodigi_key or os.environ.get("PRODIGI_API_KEY")
    now = now or time.time()
    shop = shop or load_shop()
    counts = {"in production": 0, "shipped": 0, "awaiting approval": 0, "digital emailed": 0, "needs attention": 0}
    link_days = int((shop.get("digital") or {}).get("link_days") or 30)
    notes = list(config_problems(shop))
    params = {"limit": 100, "created[gte]": int(now - days * 86400), "expand[]": "data.payment_intent"}
    while True:
        page = stripe_get(http, key, "/checkout/sessions", params=params)
        for s in page.get("data", []):
            if s.get("payment_status") != "paid" or not (s.get("metadata") or {}).get("recipe"):
                continue
            pi = s.get("payment_intent") or {}
            meta, pid = pi.get("metadata") or {}, pi.get("id", "")
            age_h = (now - int(s.get("created") or now)) / 3600
            if (s.get("metadata") or {}).get("product") == "digital":
                if meta.get("digital_sent"):
                    counts["digital emailed"] += 1
                    old = [meta[k] for k in ("digital_png", "digital_pdf") if meta.get(k)]
                    if old and age_h > link_days * 24:  # links expire as promised in the email
                        uploader("del", *old)
                        stripe_set_metadata(http, key, pid, {"digital_png": "", "digital_pdf": "",
                                                             "print_status": "emailed; links expired"})
                elif age_h > 2:
                    counts["needs attention"] += 1
                    notes.append(f"{ref(pid)}: digital file not emailed (see the payment in Stripe)")
                continue
            if meta.get("print_status") == "shipped":
                counts["shipped"] += 1
                continue
            if not meta.get("prodigi_order"):
                if meta.get("print_error") or (not meta.get("print_file") and age_h > 2):
                    counts["needs attention"] += 1
                    notes.append(f"{ref(pid)}: not sent to print (see the payment in Stripe)")
                else:
                    counts["awaiting approval"] += 1
                    if age_h > APPROVAL_GRACE_HOURS:
                        notes.append(f"{ref(pid)}: waiting for approval for over {APPROVAL_GRACE_HOURS} hours")
                continue
            if not prodigi_key:
                notes.append("PRODIGI_API_KEY isn't set, so orders at Prodigi can't be checked")
                break
            r = http.get(f"{prodigi_base()}/orders/{meta['prodigi_order']}", headers={"X-API-Key": prodigi_key}, timeout=60)
            if r.status_code >= 400:
                counts["needs attention"] += 1
                notes.append(f"{ref(pid)}: Prodigi lookup failed (HTTP {r.status_code})")
                continue
            o = r.json().get("order") or {}
            stage = (o.get("status") or {}).get("stage", "")
            issues = (o.get("status") or {}).get("issues") or []
            tracking = [sh.get("tracking", {}).get("url") for sh in o.get("shipments") or []
                        if sh.get("status") == "Shipped" and (sh.get("tracking") or {}).get("url")]
            if tracking:
                stripe_set_metadata(http, key, pid, {"print_status": "shipped", "tracking": tracking[0]})
                if not meta.get("email_shipped"):
                    title = json.loads(s["metadata"]["recipe"]).get("title") or "your map"
                    notify(http, key, pid, (s.get("customer_details") or {}).get("email"), "email_shipped",
                           shipped_email(title, tracking[0]))
                old = [meta["print_file"], f"orders/{pid}-preview.png"] if meta.get("print_file") else []
                if old:
                    uploader("del", *old)
                    stripe_set_metadata(http, key, pid, {"print_file": "", "print_preview": ""})
                counts["shipped"] += 1
            elif issues or stage == "Cancelled":
                counts["needs attention"] += 1
                notes.append(f"{ref(pid)}: Prodigi reports {'a cancellation' if stage == 'Cancelled' else 'an issue'}")
            else:
                counts["in production"] += 1
        if not page.get("has_more") or not page.get("data"):
            break
        params = dict(params, starting_after=page["data"][-1]["id"])
    return {"counts": counts, "notes": notes}


# --- Command line ------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["prepare", "submit", "status"])
    p.add_argument("--session", help="Stripe Checkout session ID (cs_…)")
    p.add_argument("--github-output", help="file to write next=submit|skip to (GitHub Actions)")
    args = p.parse_args(argv)
    try:
        if args.step == "prepare":
            nxt = prepare(args.session)
            if args.github_output:
                with open(args.github_output, "a") as f:
                    f.write(f"next={nxt}\n")
        elif args.step == "submit":
            submit(args.session)
        else:
            result = status()
            lines = ["| Orders, last 45 days | Count |", "|---|---|"]
            lines += [f"| {k} | {v} |" for k, v in result["counts"].items()]
            lines += [""] + [f"- {n}" for n in result["notes"]]
            report = "\n".join(lines)
            print(report)
            if os.environ.get("GITHUB_STEP_SUMMARY"):
                with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
                    f.write(report + "\n")
            if result["notes"]:
                sys.exit(1)  # a failed run emails the repository owner
    except FulfilError as e:
        print(f"Stopped: {e}")
        sys.exit(1)
    except KeyError as e:
        print(f"Stopped: missing setting {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Stopped: network error ({type(e).__name__})")
        sys.exit(1)
    except Exception as e:  # no traceback: it could carry customer details into public logs
        print(f"Stopped: unexpected error ({type(e).__name__})")
        sys.exit(1)


if __name__ == "__main__":
    main()
