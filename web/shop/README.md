# Shared shop code

Order handling used by both print makers (`web/footprints`, `web/peaks`). Each site's
`api/` files are thin wrappers that pass in what differs: the site's `shop.json`, how
its design ("recipe") is checked, and how products are named at checkout.

No npm dependencies here: anything a site installs (such as `@vercel/blob`) is handed
in by that site's wrapper, because modules resolve from this folder, not the site's.
Vercel includes these files because the sites' functions `require` them (keep the
project setting "Include files outside the root directory" on, as it is by default).

One Stripe account, one webhook (on the footprints site) and one "Print order" workflow
serve both shops: the Checkout session's `shop` metadata says which one an order is for.
