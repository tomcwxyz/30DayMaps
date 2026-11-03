# Footprints shop (first version)

Customers design a print on the web page and pay by card. Each paid order in Stripe carries a **recipe** of the design. You turn the recipe into a print file with the GitHub form, then send it to a print company by hand. Nothing is automated after payment yet; that is deliberate while testing demand.

## How it fits together

- `web/footprints/index.html` shows **Order a print** only when it's served with its order API and the shop is open. Opened as a plain file, or on GitHub Pages, it stays a free design tool.
- `web/footprints/api/checkout.js` checks the design, prices it from `shop.json` (never from the browser) and opens Stripe Checkout with the recipe in the payment's metadata.
- `web/footprints/shop.json` holds your prices (in pence), delivery price, countries and the note shown at checkout. A size with `"price": null` isn't for sale.
- `web/footprints/thanks.html` is where customers land after paying.

## Going live

1. **Prices.** Fill in `shop.json`: price per size and the delivery price, in pence. Base them on your print company's base cost plus postage plus margin.
2. **Host.** Create a Vercel project from this repo with **Root Directory** set to `web/footprints` and no build step. Any host that runs Node functions from an `api/` folder works.
3. **Stripe key.** In the host's environment variables, set `STRIPE_SECRET_KEY`. Start with a test key (`sk_test_…`). Optionally set `SITE_URL` to your public address. The key never reaches the browser.
4. **Notifications.** In Stripe, turn on email notifications for successful payments, and customer receipts.
5. **Test.** In test mode, order a print with Stripe's test card, check the payment shows the recipe, and run it through the steps below. Then switch to your live key.

The shop opens only when the key is set, at least one size has a price and delivery has a price.

## Fulfilling an order

1. In Stripe, open the payment and copy the `recipe` value from its metadata.
2. In GitHub: **Actions → Footprints print maker → Run workflow**, paste it into **Shop order**, run.
3. Download the artifact. Upload the 300 dpi PNG (or the PDF) to your print company, with the customer's shipping address from Stripe.
4. Send the tracking number to the customer when the print company dispatches.

The recipe always prints from OpenStreetMap, the same data the customer saw on the page, so the print matches the preview.

## Before the first real order

- **Print company file sizes.** Check the exact sizes and bleed your print company wants for each product. The renderer makes exact A-series and 50×70 cm sheets with a built-in margin but no bleed.
- **Text.** Customers write their own titles (max 60 characters, subtitle 140). Look at each recipe before printing.
- **Credit line.** The OpenStreetMap credit is part of every print and must stay.
- **Terms, privacy and VAT.** You'll hold customer names and addresses via Stripe.

## Trying it locally

    node web/footprints/test/devserver.js                     # page + API, shop closed
    MOCK_STRIPE=1 SHOP_JSON=my-prices.json node web/footprints/test/devserver.js

With `MOCK_STRIPE=1` the server answers Stripe itself and logs what would have been sent, so the whole flow can be tried without an account. Tests: `node --test web/footprints/test/*.test.js` and `python -m pytest tests/test_prints.py`.
