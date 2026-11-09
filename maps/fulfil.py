"""Turn paid shop orders (footprints and peaks) into Prodigi print orders and emailed files.

    python -m maps.fulfil prepare --session cs_...   render the print and store the file
                                                    (digital orders: render, store and email)
    python -m maps.fulfil submit  --session cs_...   send the order to Prodigi
    python -m maps.fulfil status                     check recent orders, tidy up shipped files

The "Print order" GitHub workflow runs prepare, waits for approval, then runs submit.
Digital orders finish in prepare: the files are emailed to the customer as download links.
Both print makers sell through one Stripe account. A Checkout session's `shop` metadata
says which shop an order is from (none means footprints); each shop has its own
shop.json (prices, Prodigi products, email wording, site) and its own renderer.
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
SHOP_FILES = {"footprints": SHOP_JSON, "peaks": ROOT / "web" / "peaks" / "shop.json"}
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


def shop_name(meta: dict | None) -> str:
    """Which shop an order is from: the session's `shop` metadata, or footprints for older orders."""
    name = (meta or {}).get("shop") or "footprints"
    if name not in SHOP_FILES:
        raise FulfilError("Unknown shop on this order")
    return name


def paper_of(order: "Order") -> str:
    if order.shop == "footprints":
        from maps import prints
        return prints.spec_from_recipe(order.recipe).paper
    return str(json.loads(order.recipe).get("paper", ""))


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
    name: str = ""
    shop: str = "footprints"
    route: str = ""   # peaks: encoded GPX route, carried in the session's route_0, route_1, … metadata


def load_order(http, key: str, session_id: str) -> Order:
    if not SESSION_ID.match(session_id or ""):
        raise FulfilError("That isn't a Stripe Checkout session ID (cs_…)")
    s = stripe_get(http, key, f"/checkout/sessions/{session_id}", params={"expand[]": "payment_intent"})
    return order_from_session(s)


def customer_name(s: dict) -> str:
    shipping = s.get("shipping_details") or (s.get("collected_information") or {}).get("shipping_details") or {}
    return (s.get("customer_details") or {}).get("name") or shipping.get("name") or ""


def order_from_session(s: dict) -> Order:
    if s.get("payment_status") != "paid":
        raise FulfilError("This order isn't paid")
    recipe = (s.get("metadata") or {}).get("recipe")
    if not recipe:
        raise FulfilError("This payment isn't a shop order")
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
    meta = s.get("metadata") or {}
    route, i = [], 0
    while meta.get(f"route_{i}"):
        route.append(meta[f"route_{i}"])
        i += 1
    return Order(session_id=s["id"], pi_id=pi["id"], metadata=pi.get("metadata") or {}, recipe=recipe,
                 shipping=shipping or {}, email=email, created=int(s.get("created") or 0), product=product,
                 name=customer_name(s), shop=shop_name(meta), route="".join(route))


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
            "merchantReference": f"{order.shop}-print",
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


def render_peaks(recipe: str, out: Path, kinds=("print", "web"), min_long_px: int | None = None,
                 route: str | None = None) -> dict[str, Path]:
    """Peaks prints are drawn by the web page itself, in headless Chromium."""
    from maps import peaks_render
    return peaks_render.render(recipe, out, kinds, min_long_px, route=route or None)


RENDERERS = {"footprints": render, "peaks": render_peaks}
AUTO = object()   # pick the renderer for the order's shop


RENDER_ATTEMPTS = 3
RENDER_WAIT = 30   # seconds before the 2nd try, doubling after; outside data (tiles, summit names) can be slow for a while


def _render(renderer, order: Order, out: Path, kinds, min_long_px=None) -> dict[str, Path]:
    """Draws the order's files, trying again a couple of times: a print job has nobody to press retry."""
    renderer = RENDERERS[order.shop] if renderer is AUTO else renderer
    for attempt in range(1, RENDER_ATTEMPTS + 1):
        try:
            if order.route:
                return renderer(order.recipe, out, kinds, min_long_px, route=order.route)
            return renderer(order.recipe, out, kinds, min_long_px) if min_long_px else renderer(order.recipe, out, kinds)
        except FulfilError:
            raise
        except Exception as e:
            if attempt == RENDER_ATTEMPTS:
                raise
            wait = RENDER_WAIT * 2 ** (attempt - 1)
            print(f"{ref(order.pi_id)}: render attempt {attempt} failed ({type(e).__name__}); trying again in {wait} s")
            time.sleep(wait)


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


def site_url(shop: dict | None) -> str:
    """Where a shop's emails and download links point: shop.json's site, else SITE_URL."""
    return ((shop or {}).get("site") or os.environ.get("SITE_URL", "")).rstrip("/")


def download_secret(shop_name: str = "footprints") -> str | None:
    """The key a shop's download links are signed with: <SHOP>_DOWNLOAD_SECRET if set, else DOWNLOAD_SECRET.
    It must match DOWNLOAD_SECRET on that shop's Vercel project."""
    return os.environ.get(f"{shop_name.upper()}_DOWNLOAD_SECRET") or os.environ.get("DOWNLOAD_SECRET")


def download_link(pathname: str, days: int, now: float | None = None, site: str | None = None,
                  shop_name: str = "footprints") -> str:
    """A link to the shop's /api/download for a digital file, signed to expire after `days`."""
    secret, site = download_secret(shop_name), (site or os.environ.get("SITE_URL", "")).rstrip("/")
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


def _paper_label(recipe: dict, shop: dict) -> str:
    size = (shop.get("sizes") or {}).get(recipe.get("paper")) or {}
    return size.get("label") or f"{recipe.get('paper', '')} print"


def first_name(full: str | None) -> str:
    """'Jo Bloggs' -> 'Jo'. Blank if there's nothing sensible to use."""
    word = (full or "").strip().split(" ")[0] if full else ""
    return word[:40] if word and any(ch.isalpha() for ch in word) else ""


def _letter(name: str, paras: list[str], signoff: str, site: str, brand: str = "Footprints") -> tuple[str, str]:
    """Plain-text and HTML versions of a short personal email. paras are (text, html) pairs."""
    hello = f"Hi {name}," if name else "Hello,"
    sign = [signoff, f"{brand} · {site}" if site else brand]
    text = "\n\n".join([hello] + [t for t, _ in paras] + ["\n".join(sign)])
    html = "".join([f"<p>{_esc(hello)}</p>"] + [f"<p>{h}</p>" for _, h in paras]
                   + [f"<p>{_esc(sign[0])}<br><span style=\"color:#666\">{_esc(sign[1])}</span></p>"])
    return text, html


def _voice(shop: dict) -> tuple[str, str]:
    signoff = ((shop or {}).get("email") or {}).get("signoff") or "Tom"
    site = site_url(shop).replace("https://", "")
    return signoff, site


def _copy(shop: dict | None) -> dict:
    """The words that differ between shops (shop.json "email"), with footprints' as the default."""
    e = (shop or {}).get("email") or {}
    return {"brand": e.get("brand") or "Footprints", "thing": e.get("thing") or "footprints map",
            "made": e.get("made") or "made just now from every building in OpenStreetMap"}


def digital_email(title: str, png_url: str, pdf_url: str, days: int, name: str = "", shop: dict | None = None) -> tuple[str, str, str]:
    signoff, site = _voice(shop)
    c = _copy(shop)
    subject = (f"Your map of {title} is ready" if c["brand"] == "Footprints" else f"Your print of {title} is ready")[:150]
    text, html = _letter(first_name(name), [
        (f"Thanks for buying a {c['thing']}. Here's \"{title}\", {c['made']}.",
         f"Thanks for buying a {_esc(c['thing'])}. Here's <strong>{_esc(title)}</strong>, {_esc(c['made'])}."),
        (f"The high-resolution PNG, sharp printed up to A2:\n{png_url}\n\nThe PDF, which prints sharp at any size:\n{pdf_url}",
         f'<a href="{_esc(png_url)}">Download the high-resolution PNG</a>, sharp printed up to A2.<br>'
         f'<a href="{_esc(pdf_url)}">Download the PDF</a>, which prints sharp at any size.'),
        (f"The links work for {days} days, so save the files somewhere safe. They're yours to print and frame; "
         "please keep the small map data credit on if you share it.",
         f"The links work for {days} days, so save the files somewhere safe. They're yours to print and frame; "
         "please keep the small map data credit on if you share it."),
        ("If anything's not right, just reply. It comes straight to me.",
         "If anything's not right, just reply. It comes straight to me."),
    ], signoff, site, _copy(shop)["brand"])
    return subject, text, html


def received_email(title: str, paper: str, name: str = "", shop: dict | None = None) -> tuple[str, str, str]:
    signoff, site = _voice(shop)
    subject = f"Thanks for your order: {title}"[:150]
    text, html = _letter(first_name(name), [
        (f"Thanks for ordering \"{title}\" ({paper}). I hope you love it.",
         f"Thanks for ordering <strong>{_esc(title)}</strong> ({_esc(paper)}). I hope you love it."),
        ("Every print is made to order. I check each one myself before it goes to the printer, "
         "then it's printed and posted. It usually reaches you within a week.",
         "Every print is made to order. I check each one myself before it goes to the printer, "
         "then it's printed and posted. It usually reaches you within a week."),
        ("I'll email again with a tracking link as soon as it's on its way. "
         "If you have any questions in the meantime, just reply. It comes straight to me.",
         "I'll email again with a tracking link as soon as it's on its way. "
         "If you have any questions in the meantime, just reply. It comes straight to me."),
    ], signoff, site, _copy(shop)["brand"])
    return subject, text, html


def shipped_email(title: str, tracking: str, name: str = "", shop: dict | None = None) -> tuple[str, str, str]:
    signoff, site = _voice(shop)
    subject = f"Your print is on its way: {title}"[:150]
    text, html = _letter(first_name(name), [
        (f"Good news: \"{title}\" has been printed and posted.",
         f"Good news: <strong>{_esc(title)}</strong> has been printed and posted."),
        (f"You can track it here:\n{tracking}", f'<a href="{_esc(tracking)}">Track your parcel</a>'),
        ("I hope it looks great on the wall. If anything's wrong when it arrives, just reply and I'll put it right.",
         "I hope it looks great on the wall. If anything's wrong when it arrives, just reply and I'll put it right."),
    ], signoff, site, _copy(shop)["brand"])
    return subject, text, html


def approval_email(recipe: dict, paper: str, preview_url: str, run_url: str, stripe_url: str,
                   shop: str = "footprints") -> tuple[str, str, str]:
    """For the shop owner only: what's about to be printed, with a link to approve it."""
    title = recipe.get("title") or "(no title)"
    if shop == "peaks":
        rows = [("Shop", "Peaks"), ("Title", title), ("Subtitle", recipe.get("subtitle") or "–"),
                ("Style", recipe.get("style", "?")), ("Place", recipe.get("name") or "–"),
                ("Route", f"yes, {recipe['route']} points" if recipe.get("route") else "no"),
                ("Run", " · ".join(x for x in (recipe.get("runner"), recipe.get("date"), recipe.get("time")) if x) or "–"),
                ("Sheet", f"{paper}, {recipe.get('orient', 'portrait')}, {recipe.get('theme', 'paper')} colours")]
    else:
        rows = [("Title", title), ("Subtitle", recipe.get("subtitle") or "–"), ("Small line", recipe.get("kicker") or "–"),
                ("Place", recipe.get("name") or "–"),
                ("Sheet", f"{paper}, {recipe.get('orient', 'portrait')}, {recipe.get('theme', 'paper')} colours, "
                          f"{recipe.get('width_km', '?')} km across")]
    subject = f"Approve this print? {title}, {recipe.get('paper', '')}"[:150]
    text = ("A print order is waiting for your approval.\n\n" + "\n".join(f"{k}: {v}" for k, v in rows)
            + f"\n\nPreview (link works for 7 days):\n{preview_url}\n\n"
            + (f"Approve or reject it on GitHub (Review deployments):\n{run_url}\n\n" if run_url else "")
            + (f"The payment in Stripe:\n{stripe_url}\n" if stripe_url else ""))
    table = "".join(f'<tr><td style="color:#666;padding:2px 12px 2px 0;vertical-align:top">{_esc(k)}</td>'
                    f"<td style=\"padding:2px 0\"><strong>{_esc(v)}</strong></td></tr>" for k, v in rows)
    html = ("<p>A print order is waiting for your approval.</p>"
            f'<p><a href="{_esc(preview_url)}"><img src="{_esc(preview_url)}" alt="Preview of the print" '
            'style="max-width:420px;width:100%;border:1px solid #ddd"></a></p>'
            f"<table>{table}</table>"
            + (f'<p style="margin-top:18px"><a href="{_esc(run_url)}" style="background:#2e6b5e;color:#fff;'
               'padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:bold">Approve or reject on GitHub</a></p>'
               '<p style="color:#666">On the run, press <em>Review deployments</em>, tick print-orders, then approve or reject.</p>'
               if run_url else "")
            + (f'<p><a href="{_esc(stripe_url)}">See the payment in Stripe</a></p>' if stripe_url else "")
            + '<p style="color:#666">The preview link works for 7 days.</p>')
    return subject, text, html


def approval_links(pi_id: str, key: str) -> tuple[str, str]:
    """The GitHub run this is happening in, and the payment in the Stripe dashboard."""
    server, repo, run = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    run_url = f"{server}/{repo}/actions/runs/{run}" if server and repo and run else ""
    test = "_test_" in (key or "")
    stripe_url = f"https://dashboard.stripe.com/{'test/' if test else ''}payments/{pi_id}"
    return run_url, stripe_url


def sender_for(shop: dict | None) -> str | None:
    """SHOP_EMAIL_FROM with the shop's own display name (shop.json email.from_name), same address."""
    sender, name = os.environ.get("SHOP_EMAIL_FROM"), ((shop or {}).get("email") or {}).get("from_name")
    if not sender or not name:
        return sender
    address = sender[sender.find("<") + 1:sender.rfind(">")] if "<" in sender else sender.strip()
    return f"{name} <{address}>"


def notify(http, key: str, pid: str, to: str | None, flag: str, message: tuple[str, str, str], shop: dict | None = None) -> bool:
    """Send an order update once, noting it on the payment. A failed update never holds up the order."""
    if not to:
        return False
    try:
        send_email(http, to, *message, idempotency=f"{flag}-{pid}", sender=sender_for(shop))
    except FulfilError as e:
        print(f"{ref(pid)}: customer update not sent ({e})")
        return False
    stripe_set_metadata(http, key, pid, {flag: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return True


def send_email(http, to: str, subject: str, text: str, html: str, idempotency: str, sender: str | None = None):
    key, sender = os.environ.get("RESEND_API_KEY"), sender or os.environ.get("SHOP_EMAIL_FROM")
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

def prepare(session_id: str, *, http=requests, key=None, uploader=blob, renderer=AUTO, shop=None) -> str:
    """Render and store the print. Returns 'submit', or 'skip' when nothing more is needed."""
    key = key or os.environ["STRIPE_SECRET_KEY"]
    order = load_order(http, key, session_id)
    shop = shop or load_shop(SHOP_FILES[order.shop])
    if order.product == "digital":
        return deliver_digital(order, http=http, key=key, uploader=uploader, renderer=renderer, shop=shop)
    if order.metadata.get("prodigi_order"):
        print(f"{ref(order.pi_id)}: already sent to print; nothing to do")
        return "skip"
    sku_for(shop, paper_of(order))  # fail early if the size can't be printed
    if not order.metadata.get("email_received"):
        recipe = json.loads(order.recipe)
        if notify(http, key, order.pi_id, order.email, "email_received",
                  received_email(recipe.get("title") or "your map", _paper_label(recipe, shop), order.name, shop), shop):
            print(f"{ref(order.pi_id)}: order confirmation emailed")
    if order.metadata.get("print_file"):
        print(f"{ref(order.pi_id)}: print file already made; waiting for approval")
        return "submit"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            files = _render(renderer, order, Path(tmp), ("print", "web"))
            print_path = uploader("put", str(files["print"]), f"orders/{order.pi_id}-print.png")["pathname"]
            preview_path = uploader("put", str(files["web"]), f"orders/{order.pi_id}-preview.png")["pathname"]
            preview_url = signed_url(uploader, preview_path, PREVIEW_HOURS)
    except FulfilError:
        raise
    except Exception as e:  # keep tracebacks (which can contain URLs) out of public logs
        detail = re.sub(r"(https?|file)://\S+", "<url>", str(e)).strip().splitlines()
        detail = next((l for l in detail if l.strip() and not l.lstrip().startswith(("at ", "Call log", "-"))), "")[:240]
        raise FulfilError(f"Rendering the print failed ({type(e).__name__}{': ' + detail if detail else ''})") from None
    stripe_set_metadata(http, key, order.pi_id, {
        "print_status": "awaiting approval", "print_file": print_path, "print_preview": preview_url, "print_error": ""})
    print(f"{ref(order.pi_id)}: print rendered and stored; preview link saved on the payment in Stripe")
    owner = os.environ.get("SHOP_OWNER_EMAIL") or os.environ.get("SHOP_REPLY_TO")
    if owner and not order.metadata.get("email_owner"):
        recipe = json.loads(order.recipe)
        if notify(http, key, order.pi_id, owner, "email_owner",
                  approval_email(recipe, _paper_label(recipe, shop), preview_url, *approval_links(order.pi_id, key), order.shop)):
            print(f"{ref(order.pi_id)}: preview emailed to the shop owner for approval")
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
                files = _render(renderer, order, Path(tmp), ("print", "pdf"), DIGITAL_MIN_LONG_PX)
                png_path = uploader("put", str(files["print"]), f"digital/{order.pi_id}-print.png")["pathname"]
                pdf_path = uploader("put", str(files["pdf"]), f"digital/{order.pi_id}-print.pdf")["pathname"]
            stripe_set_metadata(http, key, order.pi_id, {"print_status": "file made, emailing",
                                                         "digital_png": png_path, "digital_pdf": pdf_path})
    except FulfilError:
        raise
    except Exception as e:
        raise FulfilError(f"Rendering the digital file failed ({type(e).__name__})") from None
    title = json.loads(order.recipe).get("title") or "your map"
    site = site_url(shop)
    png_url, pdf_url = (download_link(p, days, site=site, shop_name=order.shop) for p in (png_path, pdf_path))
    send_email(http, order.email, *digital_email(title, png_url, pdf_url, days, order.name, shop), idempotency=f"digital-{order.pi_id}",
               sender=sender_for(shop))
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
    shop = shop or load_shop(SHOP_FILES[order.shop])
    payload = order_payload(order, sku_for(shop, paper_of(order)), shipping_method(shop), file_url)
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
    shops = {}

    def shop_for(name):   # a shop passed in (tests) stands for every order
        if name not in shops:
            shops[name] = shop or load_shop(SHOP_FILES[name])
        return shops[name]

    counts = {"in production": 0, "shipped": 0, "awaiting approval": 0, "digital emailed": 0, "needs attention": 0}
    notes = []
    for name in (["footprints"] if shop else SHOP_FILES):
        notes += [p if shop else f"{name}: {p}" for p in config_problems(shop_for(name))]
    params = {"limit": 100, "created[gte]": int(now - days * 86400), "expand[]": "data.payment_intent"}
    while True:
        page = stripe_get(http, key, "/checkout/sessions", params=params)
        for s in page.get("data", []):
            if s.get("payment_status") != "paid" or not (s.get("metadata") or {}).get("recipe"):
                continue
            pi = s.get("payment_intent") or {}
            meta, pid = pi.get("metadata") or {}, pi.get("id", "")
            try:
                sh = shop_for(shop_name(s.get("metadata")))
            except FulfilError as e:
                counts["needs attention"] += 1
                notes.append(f"{ref(pid)}: {e}")
                continue
            link_days = int((sh.get("digital") or {}).get("link_days") or 30)
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
                           shipped_email(title, tracking[0], customer_name(s), sh), sh)
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
