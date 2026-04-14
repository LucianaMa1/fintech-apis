# Fintech APIs

A curated, machine-readable list of fintech APIs.

This project is inspired by [public-apis/public-apis](https://github.com/public-apis/public-apis), but narrowed to one domain only: financial services and financial infrastructure APIs.

## Scope

The original `public-apis` project is a broad directory of public APIs across many categories. Its real scope is:

- community-curated API discovery
- lightweight metadata, not deep documentation
- free access or at least a meaningful free tier
- simple tabular browsing by category
- quick evaluation fields such as auth, HTTPS, and CORS

This project keeps that spirit, but focuses only on fintech.

## What counts as fintech here

We include APIs that help developers build financial products, workflows, or infrastructure, such as:

- payments and payouts
- banking and open banking
- cards and issuing
- identity, KYC, KYB, AML, and fraud
- treasury and account infrastructure
- lending and underwriting
- insurance infrastructure
- tax and invoicing
- market data and brokerage infrastructure
- crypto and digital asset infrastructure
- accounting and financial operations

## What does not belong

To keep the catalogue focused, we do not include:

- general business SaaS APIs with only incidental billing features
- generic ecommerce APIs unless the API itself is primarily financial infrastructure
- personal finance content sites with no real developer platform
- APIs that are effectively unusable without buying proprietary hardware first
- pure marketing pages with weak or missing docs
- products with no public access path and no free tier or test/sandbox access

## Design Principles

- Vertical focus: one domain only, much deeper than a general API list
- Human + machine readable: easy to browse, easy to index
- Faceted metadata: not just one category tree
- Practical evaluation: developers should be able to compare APIs quickly
- Compliance-aware: fintech needs fields beyond `Auth / HTTPS / CORS`

## Core Metadata

Each API record should have, at minimum:

- `name`
- `website`
- `docs`
- `description`
- `category`
- `subcategories`
- `auth`
- `https`
- `cors`
- `pricing_model`
- `sandbox`
- `regions`
- `compliance`
- `data_sensitivity`
- `status`

## Fintech Facets

Unlike the original `public-apis` list, this repo uses fintech-specific facets.

### F1. Function

- payments
- payouts
- card_issuing
- card_processing
- open_banking
- bank_accounts
- identity_kyc
- kyb
- aml_screening
- fraud_risk
- lending
- underwriting
- insurance
- tax
- invoicing
- accounting
- treasury
- market_data
- brokerage
- crypto_on_off_ramp
- wallet_infrastructure

### F2. Regulatory model

- vendor_licensed
- no_license_needed
- needs_customer_license
- partner_bank_model

### F3. Jurisdiction

- global
- us
- uk
- eu
- apac
- latam
- mea
- country-level ISO codes where relevant

### F4. Data sensitivity

- l0_public
- l1_business
- l2_identity
- l3_financial_account
- l4_transactional

### F5. Integration mode

- rest
- graphql
- webhooks
- file_transfer
- sdk_only
- embedded_ui

### F6. Buyer type

- startup
- smb
- enterprise
- fintech_platform
- bank

### F7. Pricing model

- free
- freemium
- pay_per_call
- pay_per_verification
- saas_subscription
- custom_enterprise
- revenue_share

## Suggested Repository Structure

```text
.
├── README.md
├── CONTRIBUTING.md
├── data
│   ├── apis.seed.json
│   └── taxonomy.json
├── favicon.svg
├── index.html
├── styles.css
└── app.js
```

## Record Format

Example:

```json
{
  "id": "example-payments-api",
  "name": "Example Payments",
  "website": "https://example.com",
  "docs": "https://docs.example.com",
  "description": "Accept payments and manage payouts for internet businesses.",
  "category": "payments",
  "subcategories": ["payouts"],
  "auth": "apiKey",
  "https": true,
  "cors": "Unknown",
  "sandbox": true,
  "pricing_model": ["custom_enterprise", "pay_per_call"],
  "regions": ["US", "EU"],
  "regulatory_model": "vendor_licensed",
  "compliance": ["PCI-DSS", "SOC 2"],
  "data_sensitivity": "l4_transactional",
  "integration_mode": ["rest", "webhooks"],
  "status": "active"
}
```

## How this differs from public-apis

- narrower domain
- richer metadata
- compliance and jurisdiction aware
- better suited for semantic search and agent workflows
- can evolve from a markdown list into a structured catalogue without changing the core mission

## Initial Direction

If we keep following the `public-apis` spirit but make it useful for fintech buyers and builders, the MVP should be:

1. a curated seed list of fintech APIs
2. a clear inclusion policy
3. a stable taxonomy
4. a machine-readable JSON dataset
5. a lightweight browse/search UI

## Local preview

The repository now includes a first usable static catalogue UI:

- `index.html`
- `styles.css`
- `app.js`
- `data/apis.seed.json`

To preview it locally, run a static server in the repo root and open `http://localhost:8000`.

Example:

```bash
python3 -m http.server 8000
```

The website now reads API entries directly from `data/apis.seed.json`, so adding or editing APIs only requires changing that one file.

## Deploying to Cloudflare Pages

This repo is ready for static deployment on Cloudflare Pages.

- Framework preset: `None`
- Build command: none
- Build output directory: `.`
- Root directory: `/`

You can connect the GitHub repository in Cloudflare Pages and deploy directly from the default branch.

This repo also includes a minimal `wrangler.toml` with:

- `name = "fintech-apis"`
- `pages_build_output_dir = "."`

If you later want cleaner production docs pages, we can replace markdown links in the navbar with dedicated HTML pages.
