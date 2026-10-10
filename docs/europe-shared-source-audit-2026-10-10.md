# Europe shared-source audit — 10 October 2026

## EFFIS / Copernicus Emergency Management Service

| Check | Finding | Primary evidence |
| --- | --- | --- |
| Rights | EU-owned site content defaults to CC BY 4.0 with attribution and indication of changes; individual third-party notices can differ. | [EFFIS data license](https://forest-fire.emergency.copernicus.eu/about-effis/data-license) |
| Current active-fire layer | EFFIS states its active-fire detections come from NASA FIRMS. It filters a subset of MODIS/VIIRS thermal hotspots; some hotspots are other heat sources and some fires go undetected. | [EFFIS active-fire method](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/active-fire-detection) |
| Current delivery | EFFIS lists active-fire and burnt-area layers and describes access through WMS. The burnt-area database has a real-time download. | [Data and services](https://forest-fire.emergency.copernicus.eu/applications/data-and-services), [download instructions](https://forest-fire.emergency.copernicus.eu/downloads-instructions) |
| Country incident database | The European Fire Database collects annual submissions from participating countries. Public access currently exposes general information, such as yearly fire-count maps, rather than a verified current individual-incident feed. | [European Fire Database](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/european-fire-database) |

**Decision:** Do not ingest EFFIS active-fire detections as independent agency incidents or as independent confirmation of the existing FIRMS observations. Its documented active-fire source is FIRMS, so adding it as another confirmation would double-count one satellite family. The published burnt-area product is a different, later observation; it does not fill the current agency-incident gap. No provider requests or publication changes follow from this audit.

The 52-row national inventory remains open. Each national feed still needs a verified endpoint, individual incident identity, time field, usage rights, and bounded collection cost before an adapter can be added. The absence of a verified feed is an evidence gap, not proof that no such feed exists.
