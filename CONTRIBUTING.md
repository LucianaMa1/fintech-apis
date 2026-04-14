# Contributing

This project follows the spirit of `public-apis/public-apis`, with fintech-specific rules.

## Acceptance Criteria

An API should satisfy most of the following:

- clearly belongs to financial infrastructure or financial operations
- has public documentation
- has a usable sandbox, test mode, or meaningful free tier
- can be evaluated by an external developer without a sales call
- has enough product clarity to classify by function, region, and compliance posture

## Rejection Criteria

Submissions may be rejected if they are:

- thinly disguised marketing entries
- undocumented or doc-gated
- impossible to test without purchasing unrelated hardware
- too generic to be considered fintech infrastructure
- duplicates of existing records

## Required Fields

Every submission should include:

- `name`
- `website`
- `docs`
- `description`
- `category`
- `auth`
- `https`
- `cors`
- `sandbox`
- `pricing_model`
- `regions`
- `regulatory_model`
- `status`

## Description Rules

- keep descriptions under 120 characters when possible
- describe the product capability, not the company slogan
- avoid hype words like "best", "world-class", or "revolutionary"

## Taxonomy Rules

- choose one primary `category`
- use `subcategories` for secondary capabilities
- do not overload one field with multiple meanings
- prefer explicit region codes over vague labels when known

## Data Quality Rules

- link to docs, not just the homepage, when possible
- mark `cors` as `Unknown` if it is not clearly documented
- use `vendor_licensed` only when the vendor provides the regulated layer
- use `needs_customer_license` when the buyer must already hold the regulatory permission

## Pull Request Guidance

- keep entries alphabetized within a category if editing markdown tables later
- avoid renaming existing IDs unless necessary
- explain any non-obvious compliance or region classification in the PR description
