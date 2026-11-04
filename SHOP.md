# Footprints shop

Customers design a print on the web page and pay by card. Stripe tells the shop, a GitHub workflow renders the print, waits for your approval, and sends the order to Prodigi, who print and post it. A daily check records tracking and flags anything stuck.

## How an order flows

1. **Pay.** `web/footprints/api/checkout.js` checks the design, prices it from `shop.json` and opens Stripe Checkout. The design's **recipe** is saved on the payment.
2. **Start.** Stripe calls `api/stripe-webhook.js`. It re-checks the event with Stripe (so a forged call can't start a print) and starts the **Print order** workflow with the Checkout session ID.
3. **Render.** `python -m maps.fulfil prepare` renders the 300 dpi print, stores it in Vercel Blob, and saves a preview link on the payment in Stripe (`print_preview`).
4. **Approve.** The workflow pauses for your approval. GitHub emails you; check the preview link on the payment in Stripe, then press **Approve and deploy** on the run.
5. **Print.** `python -m maps.fulfil submit` creates the Prodigi order. It's keyed to the Stripe payment, so the same order can't be printed twice. The Prodigi order ID is saved on the payment (`prodigi_order`).
6. **Track.** The daily **Print orders check** saves the tracking link on the payment once Prodigi ships it, deletes the print file, and fails (so GitHub emails you) if an order has a problem or has waited over two days for approval.

Stripe is the record: each payment's metadata shows `print_status` and any `print_error`.

**Privacy.** This repository is public, so its Actions logs are public too. The workflows print no names, addresses, emails or map titles, and upload no files to GitHub. Detail stays in Stripe; print files sit in Vercel Blob under long random addresses and are deleted after shipping.

## Setting it up

You need accounts with Stripe, Prodigi and Vercel. Do it all in test mode first.

**Shop settings** in `web/footprints/shop.json`:
- `price` per size and the `shipping` price, in pence. A size with no price isn't for sale.
- `prodigi_sku` per size you sell: the Prodigi product code, from their product catalogue or dashboard. The renderer makes the exact paper size with a built-in margin, and Prodigi fills the print area, so a little trimmed for bleed comes off the margin, not the map.
- `fulfilment.shipping_method`: one of Budget, Standard, StandardPlus, Express, Overnight.

**Vercel** (hosts the page and the two functions):
1. New project from this repo, **Root Directory** `web/footprints`, no build step.
2. Create a **Blob** store for the project (Storage tab) and copy its `BLOB_READ_WRITE_TOKEN`.
3. Environment variables: `STRIPE_SECRET_KEY`, `GITHUB_TOKEN` (a fine-grained token for this repository only, with **Actions: read and write**), and optionally `SITE_URL`.

**Stripe:**
1. Developers → Webhooks → add endpoint `https://<your site>/api/stripe-webhook`, events `checkout.session.completed` and `checkout.session.async_payment_succeeded`.
2. Turn on customer receipts and your own payment notifications.

**GitHub** (Settings of this repository):
1. Secrets → Actions: `STRIPE_SECRET_KEY`, `PRODIGI_API_KEY`, `BLOB_READ_WRITE_TOKEN`.
2. Environments → New environment `print-orders` → add yourself under **Required reviewers**, and limit it to the `main` branch.
3. Variables → Actions: `PRINT_ORDERS` = `on`. Until this is set, orders stop after rendering.
4. Leave `PRODIGI_ENV` unset while testing: orders go to Prodigi's sandbox, which doesn't print, post or charge.

**Prodigi:** add a payment method to your account, or live orders wait on hold. If your account offers branded customer emails, turn them on so customers get dispatch and tracking emails.

## Testing, then going live

1. With Stripe test keys and the Prodigi sandbox, order a print using Stripe's test card `4242 4242 4242 4242`.
2. Check: the Print order run starts, the preview link appears on the test payment, approving sends a sandbox order to Prodigi, and `prodigi_order` appears on the payment.
3. To go live: switch Vercel's and GitHub's `STRIPE_SECRET_KEY` to live keys, add a live Stripe webhook, put a live `PRODIGI_API_KEY` in GitHub, and set the variable `PRODIGI_ENV` = `live`.

## When something goes wrong

- **A run failed.** GitHub emails you. The log says which step stopped; the detail is in `print_error` on the payment in Stripe. Fix the cause and **Re-run** the workflow, or run **Print order** by hand with the Checkout session ID (`cs_…`) from Stripe.
- **Stripe couldn't reach the webhook.** Stripe retries for three days. You can also start **Print order** by hand.
- **Skip approval.** Remove yourself as a reviewer on `print-orders`. Orders then go straight to print; you lose the chance to check customers' titles first.

## Local testing

    node web/footprints/test/devserver.js                      # page and API, shop closed
    MOCK_STRIPE=1 SHOP_JSON=my-prices.json node web/footprints/test/devserver.js

With `MOCK_STRIPE=1` the server stands in for Stripe and GitHub and logs what would be sent. Tests: `node --test web/footprints/test/*.test.js` and `python -m pytest tests/test_prints.py tests/test_fulfil.py`.
