---
sidebar_position: 27
description: "Show your Shopify store's sales, orders, latest order, and low stock on your split-flap display, with an alert page for every new order."
keywords: [FiestaBoard Shopify, Shopify sales display, Shopify orders, new order alert, low stock alert, Vestaboard Shopify, split-flap Shopify]
---

# Shopify

Show your Shopify store's sales, orders, latest order, and low stock on your board, with a page that pops up for every new order.

<BoardShot plugin="shopify" alt="Shopify store sales and orders on split-flap board" />

## Overview

The Shopify plugin shows:

- Sales, order count, and average order for today, this week, or this month
- Your latest order and how long ago it came in
- How many products are running low, and which one has the least stock (optional)
- A **NEW ORDER** page that interrupts the board when an order comes in (optional)

It only reads from your store. It never changes orders, products, or settings.

Totals start at midnight in your **store's** timezone, set in Shopify under **Settings > General**. Cancelled orders are skipped, and so are test orders unless you turn them on.

## Setup

The plugin signs in with a small, read-only app that you create for your own store. It needs no redirect URL, so it works on a board that lives on your home or office network.

### 1. Create an App in the Shopify Dev Dashboard

1. Go to the [Shopify Dev Dashboard](https://dev.shopify.com/dashboard/) and sign in with the account that owns your store
2. Open **Apps** and create a new app, for example `FiestaBoard`
3. In the app's version configuration, select the **Admin API access scopes** `read_orders`, and `read_products` if you want low-stock tracking
4. **Release** the version so the scopes take effect
5. **Install** the app on your store
6. Open the app's **Settings** and copy the **Client ID** and **Client secret**

Treat the Client secret like a password: it gives read access to your store's orders. The app and the store must belong to the same Shopify organization, so create the app while signed in to the organization that owns the store.

### 2. Enable in the Web UI

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Shopify** on
4. Enter your **Store Domain**, for example `your-store.myshopify.com` (in Shopify under **Settings > Domains**; your custom domain won't work here)
5. Paste the **Client ID** and **Client Secret**
6. Optionally, choose a **Sales Period**, set a **Low Stock Threshold**, and adjust **New Order Alerts**
7. Click **Save Changes**

If you already have a custom app created in the Shopify admin before 2026, you can paste its **Admin API access token** (it starts with `shpat_`) instead of a Client ID and secret. Shopify no longer lets you create new apps that way.

On a development store, every order is a test order. Turn on **Include Test Orders** to see them.

## New Order Alerts

When an order comes in, the board shows a **NEW ORDER** page with the order number and total for about a minute, then goes back to what it was showing. Alerts appear within one refresh of the order (every 2 minutes by default).

- Each order is announced once, and orders placed before FiestaBoard started are never announced
- Several orders arriving together share one `2 NEW ORDERS` alert
- To design your own alert page, create a page that uses `{{shopify.last_order_number}}` and `{{shopify.last_order_total}}`, then choose it as the **Alert Page** in the plugin settings

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{shopify.sales_line}}` | Period and sales together | `TODAY $1,284` |
| `{{shopify.sales_display}}` | Sales in whole currency units | `$1,284` |
| `{{shopify.sales}}` | Sales with cents | `1284.50` |
| `{{shopify.period_label}}` | `TODAY`, `THIS WEEK`, or `THIS MONTH` | `TODAY` |
| `{{shopify.orders_line}}` | Order count with the word ORDERS | `23 ORDERS` |
| `{{shopify.order_count}}` | Number of orders | `23` |
| `{{shopify.avg_order_display}}` | Average order value | `$56` |
| `{{shopify.last_order_line}}` | Latest order number, total, and age | `#1042 $86 12M AGO` |
| `{{shopify.last_order_number}}` | Latest order number | `#1042` |
| `{{shopify.last_order_total}}` | Latest order total | `$86` |
| `{{shopify.last_order_ago}}` | How long ago the latest order came in | `12M AGO` |
| `{{shopify.low_stock_line}}` | Low-stock summary | `4 LOW STOCK` |
| `{{shopify.low_stock_count}}` | Variants at or below the threshold | `4` |
| `{{shopify.low_stock_item}}` | Variant with the least stock | `CERAMIC MUG BLUE` |
| `{{shopify.low_stock_item_qty}}` | Units left of that variant | `2` |
| `{{shopify.store_name}}` | Store name | `MY TEST STORE` |
| `{{shopify.currency}}` | Currency code | `USD` |

Amounts are rounded to whole units. Currencies written with `$` show `$1,284`; others show their code, such as `EUR 1,284`, because the board has no other currency symbols.

A Flagship layout, center-aligned:

```text
{{shopify.store_name}}

{66} {{shopify.sales_line}}
{{shopify.orders_line}} AVG {{shopify.avg_order_display}}
{{shopify.last_order_line}}
{{shopify.low_stock_line}}
```

## Next Steps

- [Shopify plugin setup guide](https://github.com/Fiestaboard/fiestaboard-plugin--shopify/blob/main/docs/SETUP.md) -- Settings reference and troubleshooting
- [Page Editor](/docs/features/page-editor) -- Create your store dashboard layout
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
