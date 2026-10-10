# MTG public-collector audit — 10 October 2026

## Verified source facts

- EUMETSAT lists the MTG FCI FIR CAP collection as `EO:EUM:DAT:0801` and the netCDF collection as `EO:EUM:DAT:0682`. Its catalogue labels both `NoConditions` in the [CAP](https://api.eumetsat.int/data/browse/collections/EO%3AEUM%3ADAT%3A0801?format=html) and [netCDF](https://api.eumetsat.int/data/browse/collections/EO%3AEUM%3ADAT%3A0682?format=html) listings. These catalogue pages were indexed by search but returned HTTP 404 in a direct read during this audit, so product-specific licensing still needs a successful live check before publication.
- The [official FIR product guide](https://user.eumetsat.int/resources/user-guides/mtg-fci-l2-fir-data-guide) describes both formats, a nominal ten-minute cycle, and Data Store distribution. A CAP alert describes an observed pixel; it is not a confirmed agency incident or a forecast of fire spread.
- The [Data Store FAQ](https://user.eumetsat.int/resources/user-guides/frequently-asked-questions-for-data-store) says new users receive free and unrestricted collections by default, while restricted collections require a separate licence. HTTP 429 is used when service limits are exceeded.
- The public GitHub repository currently has no EUMETSAT secret. The existing hosted collector has only FIRMS and Cloudflare credentials.

## Decision

MTG is **not enabled** in the public collector. Product-specific rights look promising, but an authenticated read, measured CAP or netCDF payload, bounded request cadence, credential availability, and resulting snapshot size have not been verified in this deployment. The 5 MiB Cloudflare KV value ceiling and 1 GB Free storage ceiling remain hard publication gates. No paid EUMETSAT or Cloudflare service may be activated to fill this gap.

If a later pilot succeeds, MTG observations must remain a separate satellite source with their own time, coverage, confidence and missing-cycle status. They must not be labelled as official incidents or independent proof that a particular FIRMS candidate is a wildfire.
