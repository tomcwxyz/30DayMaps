# Footprints and Peaks shops

Two print makers, one shop system. Everything below describes footprints; [Peaks](#peaks) covers what's the same and what differs for `web/peaks`.

Customers design a print on the web page and choose a **printed copy** or a **digital file** (£5 by default). Stripe tells the shop and a GitHub workflow takes over. For prints it renders the file, waits for your approval, and sends the order to Prodigi, who print and post it. For digital files it renders a high-resolution PNG and a PDF and emails the customer download links, with no approval step. A daily check records tracking, expires old download links and flags anything stuck.

## How an order flows

1. **Pay.** `web/footprints/api/checkout.js` checks the design, prices it from `shop.json` and opens Stripe Checkout. The design's **recipe** is saved on the payment.
2. **Start.** Stripe calls `api/stripe-webhook.js`. It re-checks the event with Stripe (so a forged call can't start a print) and starts the **Print order** workflow with the Checkout session ID.
3. **Render.** `python -m maps.fulfil prepare` renders the 300 dpi print, stores it in the private Vercel Blob store, and saves a week-long preview link on the payment in Stripe (`print_preview`).
4. **Approve.** The workflow pauses for your approval. GitHub emails you; check the preview link on the payment in Stripe, then press **Approve and deploy** on the run.
5. **Print.** `python -m maps.fulfil submit` gives Prodigi a three-day link to the print file and creates the order. It's keyed to the Stripe payment, so the same order can't be printed twice. The Prodigi order ID is saved on the payment (`prodigi_order`).
6. **Track.** The daily **Print orders check** saves the tracking link on the payment once Prodigi ships it, deletes the print file, and fails (so GitHub emails you) if an order has a problem or has waited over two days for approval.

**Digital files.** The same workflow renders a PNG (at least 7,016 pixels on the long side, so sharp printed up to A2, whatever paper size was chosen) and a vector PDF, stores both in Vercel Blob and emails the customer links through Resend. The links go to the shop's `/api/download`, which checks they're genuine and in date (signed with `DOWNLOAD_SECRET`) and then hands out a short-lived link to the file. They work for `digital.link_days` (30 by default); the daily check deletes the files after that. Digital orders skip approval because the file only goes to the buyer. Checkout shows `digital_note`, which says the file is sent straight away and the 14-day cancellation right ends once it's sent. UK law requires the buyer's express agreement to that, so check the wording suits you.

**Approval email.** Each print order also emails you (`SHOP_OWNER_EMAIL`, or `SHOP_REPLY_TO` if that's unset) an "Approve this print?" message with the preview image, the customer's words and the size, and a button to the GitHub run. It only goes to you; nothing personal appears in the public GitHub logs. Rejecting a run stops the order there: refund the customer in Stripe and reply to them.

**Customer emails.** Print buyers get an "Order received" email when the order starts and an "On its way" email with the tracking link when Prodigi ships it (sent by the daily check, so up to a day after dispatch). Both go through Resend from `SHOP_EMAIL_FROM`; a failed email is noted in the run log but never holds up the order. Turn on Stripe's own receipts too, for the payment itself.

Stripe is the record: each payment's metadata shows `print_status` and any `print_error`.

**Privacy.** This repository is public, so its Actions logs are public too. The workflows print no names, addresses, emails or map titles, and upload no files to GitHub. Detail stays in Stripe. Print files sit in a private Vercel Blob store that can only be read through signed, time-limited links, and are deleted after shipping.

## Setting it up

You need accounts with Stripe, Prodigi and Vercel. Do it all in test mode first.

**Shop settings** in `web/footprints/shop.json`:
- `price` per size and the `shipping` price, in pence. A size with no price isn't for sale.
- `prodigi_sku` per size you sell: the Prodigi product code, from their product catalogue or dashboard. The renderer makes the exact paper size with a built-in margin, and Prodigi fills the print area, so a little trimmed for bleed comes off the margin, not the map.
- `fulfilment.shipping_method`: one of Budget, Standard, StandardPlus, Express, Overnight.
- `digital.price` (500 = £5) and `digital.link_days`. Set the price to `null` to stop selling digital files. The shop can sell digital files alone, before any print sizes are priced.

**Vercel** (hosts the page and the two functions):
1. New project from this repo, **Root Directory** `web/footprints`, no build step.
2. Connect a **private Blob** store to the project (Storage tab). The place cache uses the same store. Copy the store's read-write token (`BLOB_READ_WRITE_TOKEN`, shown on the store's page) for GitHub below.
3. Environment variables: `STRIPE_SECRET_KEY`, `GITHUB_TOKEN` (a fine-grained token for this repository only, with **Actions: read and write**), `DOWNLOAD_SECRET` (any long random string, e.g. from `openssl rand -base64 32`; the same value goes in GitHub) and `SITE_URL` (the site's address, e.g. `https://30daymaps-footprints.vercel.app`).

**Stripe:**
1. Developers → Webhooks → add endpoint `https://<your site>/api/stripe-webhook`, events `checkout.session.completed` and `checkout.session.async_payment_succeeded`.
2. Turn on customer receipts and your own payment notifications.

**GitHub** (Settings of this repository):
1. Secrets → Actions: `STRIPE_SECRET_KEY`, `PRODIGI_API_KEY`, `BLOB_READ_WRITE_TOKEN`, `DOWNLOAD_SECRET` (the same value as in Vercel). Variables → Actions: `SITE_URL` (the same as in Vercel).
2. Environments → New environment `print-orders` → add yourself under **Required reviewers**, and limit it to the `main` branch.
3. Variables → Actions: `PRINT_ORDERS` = `on`, once the environment above exists. Until this is set, orders stop after rendering.
4. Leave `PRODIGI_ENV` unset while testing: orders go to Prodigi's sandbox, which doesn't print, post or charge.

**Resend** (sends digital files): create an account, verify the domain you'll send from, and create an API key. In GitHub, add the secret `RESEND_API_KEY` and the variables `SHOP_EMAIL_FROM` (for example `Footprints <prints@yourdomain>`) and, optionally, `SHOP_REPLY_TO`.

**Prodigi:** add a payment method to your account, or live orders wait on hold. If your account offers branded customer emails, turn them on so customers get dispatch and tracking emails.

## Testing, then going live

1. With Stripe test keys and the Prodigi sandbox, order a print using Stripe's test card `4242 4242 4242 4242`. Then buy a digital file the same way, using your own email address.
2. Check: the Print order run starts, the preview link appears on the test payment, approving sends a sandbox order to Prodigi, and `prodigi_order` appears on the payment. For the digital file, check the email arrives and both links download.
3. To go live: switch Vercel's and GitHub's `STRIPE_SECRET_KEY` to live keys, add a live Stripe webhook, put a live `PRODIGI_API_KEY` in GitHub, and set the variable `PRODIGI_ENV` = `live`.

## When something goes wrong

- **A run failed.** GitHub emails you. The log says which step stopped; the detail is in `print_error` on the payment in Stripe. Fix the cause and **Re-run** the workflow, or run **Print order** by hand with the Checkout session ID (`cs_…`) from Stripe.
- **Stripe couldn't reach the webhook.** Stripe retries for three days. You can also start **Print order** by hand.
- **A digital email didn't arrive.** Check `print_status` on the payment. If it says `file made, emailing`, the email failed: fix the Resend setting and re-run the workflow; it reuses the stored files.
- **Skip approval.** Remove yourself as a reviewer on `print-orders`. Orders then go straight to print; you lose the chance to check customers' titles first.

## Local testing

    node web/footprints/test/devserver.js                      # page and API, shop closed
    MOCK_STRIPE=1 SHOP_JSON=my-prices.json node web/footprints/test/devserver.js

With `MOCK_STRIPE=1` the server stands in for Stripe and GitHub and logs what would be sent. Tests: `node --test web/footprints/test/*.test.js` and `python -m pytest tests/test_prints.py tests/test_fulfil.py`.

## Peaks

The Peaks print maker (`web/peaks`) sells through the same system: same Stripe account, same webhook, same **Print order** workflow, same Prodigi account, Blob store and Resend sender. The Checkout session carries `shop: peaks`, and `maps/fulfil.py` uses `web/peaks/shop.json` for that order's prices, Prodigi products, email wording (`email.brand`, `thing`, `made`, `from_name`) and site (`site`, for email sign-offs and download links).

**What's different**
- **Rendering.** Peaks prints are drawn in the browser, so the print job opens the page itself in headless Chromium (`maps/peaks_render.py`) with the order's recipe and takes its PNG (300 dpi, or at least 7,016 px for digital files), a preview and a vector PDF made from the page's SVG. The customer gets exactly what they saw. In this mode the page fails rather than printing without summit names if Overpass is down; re-run the workflow later.
- **GPX routes.** A route is thinned on the page (to fit, rounded to about a metre) as soon as it loads, so the preview is what prints. It travels in the Checkout session's metadata (`route_0`, `route_1`, …, up to 40 × 480 characters), checked by `web/peaks/api/_recipe.js`. It is stored nowhere else, and never on the payment, which keeps its metadata for progress notes. The page's "hide the first and last 250 m" option is applied before it leaves the browser.
- **Panoramas** come on two 3:1 sheets that fit standard panoramic frames: 75 × 25 cm (Prodigi `GLOBAL-FAP-10X30`, £28) and 90 × 30 cm (`GLOBAL-FAP-12X36`, £30). Prodigi has no 60 × 20 cm sheet. At November 2026 prices they cost £14.90 and £15.90 to print and post (before VAT), in line with A2's margin.
- **Shared code.** Checkout, config, download and price loading live in `web/shop/`; each site's `api/` files are thin wrappers. The webhook stays on footprints and serves both shops.

**Setting it up** (on top of the footprints setup above)
1. **Vercel**: the `30daymaps-peaks` project with **Root Directory** `web/peaks`. Keep **Settings → Build → Include files outside the root directory** on (the default): the functions use `web/shop/`.
2. Connect the **same private Blob store** as footprints to this project (Storage tab), so digital download links work here too.
3. Environment variables: `STRIPE_SECRET_KEY` (same Stripe account as footprints; a separate restricted key with Checkout Sessions write is fine), `DOWNLOAD_SECRET` (its own random value, also added in GitHub as the secret `PEAKS_DOWNLOAD_SECRET`; without that GitHub secret the workflow signs Peaks links with the shared `DOWNLOAD_SECRET`, so the values must then match), `SITE_URL` = `https://peaks.tomcw.xyz`. No `GITHUB_TOKEN`: Peaks has no webhook of its own.
4. **Stripe, GitHub, Resend, Prodigi**: nothing new. The footprints webhook already receives Peaks payments (same Stripe account) and starts the same workflow. Emails come from `SHOP_EMAIL_FROM`'s address with the name "Peaks".

**Testing:** as for footprints, with Stripe's test card, one print (with and without a GPX route) and one digital file. `node --test web/peaks/test/*.test.js`; `python web/peaks/test/harness.py suite OUT` drives the page offline; `python -m maps.peaks_render recipe.json OUT [--route …]` re-draws a recipe by hand.
