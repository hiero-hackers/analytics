# Hiero brand assets

Unmodified SVG artwork from the official Hiero website repository:
https://github.com/hiero-ledger/hiero-website/tree/main/public/images

- `hiero-logo.svg`: `Hiero-Logo-wText.svg`
- `hiero-logo-dark.svg`: `Hiero-Logo-wText-white.svg`
- `hiero-mark.svg`: `Hiero-Favicon.svg`

Retrieved September 26, 2026. Hiero branding remains the property of its respective owners. These files identify the Hiero project in its analytics dashboard.

## Organisation brands

An organisation's profile in `src/hiero_analytics/config/orgs.py` may set
`brand="<key>"`. The dashboard then shows `brand/<key>/logo.svg` (light theme)
and `brand/<key>/logo-dark.svg` (dark theme) top left while that organisation
is selected, labelled "<display name> analytics". The key must be a lower-case
slug. With no key, or when either file fails to load, the Hiero mark above is
shown instead.

Add only artwork the organisation's maintainers have approved, and record its
source here as the Hiero entry does: the URL it came from, the original file
names, the retrieval date, and the trademark owner. The CSP allows images
from `'self'` only (plus GitHub avatars), so logos must be bundled here rather
than linked.
