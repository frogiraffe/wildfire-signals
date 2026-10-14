# Sacramento station and FIRMS context — 2026-10-09 to 2026-10-11 UTC

**Status:** real-data, retrospective descriptive pilot. No fire occurrence or weather-effect model was trained. The [Batman pilot](batman-station-thermal-context-2026-10.md) remains a separate site, not a comparable fire-rate denominator.

## Research question and selection

Can the same original-pixel/NOAA-station analytical contract work in a second geography and expose unequal weather availability in the web app? The existing 12-region archive includes a fixed California circle centered at 38° N, 120° W. The official [GHCNh station list](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh-station-list.csv) (downloaded SHA-256 `812ea50bd5efd1b9cc09d5800c55825b3d43b3c5aa75ab17b2848f43b1bfaaef`) and source-year files were checked for 2026-10-09–11. Several closer Sierra stations had no October observations; Yosemite Village 12 W had temperature but only three archived pixels inside its 25 km circle. The Sacramento Metro Airport station was chosen after inspecting both weather completeness and pilot thermal counts. **This is outcome-informed site selection**, useful for an integration test and exploration, not for confirmatory regional inference.

The selected circle is 25 km around the station at 38.7006° N, 121.5947° W, elevation 7.3 m. NOAA source ID: `USW00093225`. This is a fixed-station context measurement, not an observation at each thermal pixel.

## Source and time contracts

| Input | Original evidence | Time and rights |
|---|---|---|
| NASA FIRMS NOAA-20/21 NRT original pixels | Existing five verified scan receipts, ten SHA-256-checked pixel assets and local [SQLite rollup](../../fire_public/historical_rollup.py); original archives stay outside Git. | Original acquisition time and first capture are separate. Candidates are 0.05° cell × UTC hour, not fires, burned area or severity. [NASA use guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy). |
| NOAA NCEI GHCNh Sacramento 2026 annual PSV | [Official station-year file](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2026/psv/GHCNh_USW00093225_2026.psv), SHA-256 `2e63cb3f7ea2ca89eb52947071bd8c18cc9e4da80df5b73c808d4f25f14f5a92`; source HTTP Last-Modified 2026-10-12 13:27:17 UTC. [GHCNh documentation](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf), [dataset rights and citation](https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc%3AC01688). | Observations are UTC, with °C temperature, m/s wind and % relative humidity. Dataset metadata identifies CC0-1.0; cite NOAA NCEI. The station-year revision time is **not** each observation's first availability time. |

The join uses the latest station record at or before each archived candidate hour, at most 60 minutes old. No later weather observation is joined and no interpolation is used. The annual file is retrospective; no record is admitted as an as-of historical forecast feature. Blank weather values remain missing. Wind direction is circular and receives no arithmetic mean. A successful FIRMS request and the station's presence do not establish satellite acquisition coverage. All noncandidate hours retain unknown exposure.

## Real observations and numerical findings

| Quantity | Sacramento result | Denominator |
|---|---:|---|
| Station rows in 2026 annual source | 7,221 | One downloaded station-year file |
| Station rows in selected dates | 51 | Records through 2026-10-11 02:53 UTC; later part of the selected last day is absent |
| Original FIRMS pixels | 22 | Unique raw source records inside the selected 25 km circle and three UTC dates |
| Distinct candidate cell-hours | 10 | Deduplicated 0.05° cell × UTC hour |
| Candidate UTC hours | 6 | Five hours with prior temperature, wind speed and humidity; one lacks a station match |
| Station temperature mean | 21.612 °C | 51 station observations, not 51 independent days |
| Temperature median at candidate hours | 27.8 °C | Five matched candidate hours; outcome-selected and time-of-day-confounded |

The matched candidate-hour temperatures are **27.8, 30.0, 32.2, 21.7 and 22.8 °C**. The sixth candidate hour (2026-10-11 20:00 UTC) has no usable earlier station record in the one-hour join window and remains null. Same-hour candidate cell counts share one station value; treating ten cell-hours as ten independent weather samples would be pseudoreplication. The difference between the 27.8 °C matched median and 21.612 °C all-record mean is not an estimated temperature effect. The 51 weather records cover a different mix of times of day, and selection followed inspection of thermal counts. No correlation coefficient, regression, fire probability or inter-region risk ranking is supported. Both sites lack verified acquisition-opportunity denominators and independent wildfire outcomes.

The existing browser now allows Batman or Sacramento station selection, preserves separate source receipts and hashes, and shows each site's matched-hour and missingness denominator. If one report cannot load, the other remains available with an error notice. This is a research preview, not an operational forecast.

## Reproduce and cost

Download the exact NOAA source file outside Git and verify its SHA-256. Use the two verified public FIRMS research releases described in [the analytics roadmap](../ANALYTICS_MODELING_ROADMAP.md) to build the pixel SQLite database. Then run:

```sh
python -m fire_public.historical_rollup \
  --pixel-db /private/firms-pixels.sqlite3 \
  --regions-json examples/sacramento-region.json
python -m fire_public.environmental_analytics \
  --pixel-db /private/firms-pixels.sqlite3 \
  --regions-json examples/sacramento-region.json \
  --station-json examples/sacramento-station.json \
  --weather-psv /private/GHCNh_USW00093225_2026.psv \
  --source-url https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2026/psv/GHCNh_USW00093225_2026.psv \
  --source-last-modified 2026-10-12T13:27:17+00:00 \
  --expected-weather-sha256 2e63cb3f7ea2ca89eb52947071bd8c18cc9e4da80df5b73c808d4f25f14f5a92 \
  --start-date 2026-10-09 --end-date 2026-10-11 \
  --output-json /private/sacramento-weather-context.json
```

The pinned local replay produced byte-identical [published JSON](../../public/data/sacramento-weather-context-2026-10-11.json) in 0.138 s with 28,860 KiB peak child RSS (one local Python 3.14 run). The original 5.37 MB NOAA PSV and 240 MB research SQLite stay outside Git; the static output is 22,144 bytes. No KV write, paid service, collector change or live API call is added to the site.

## Satellite evidence blocker and next step

The prior [CMR metadata audit](batman-viirs-granule-catalog-2026-10.md) identified a 2026-10-10 NOAA-20 geolocation granule and matching active-fire product. A bounded direct GET of the original granule URL redirected to Earthdata login instead of delivering NetCDF bytes. NASA's [LANCE download help](https://nrt3.modaps.eosdis.nasa.gov/help/) explicitly requires an active login session or download token for HTTPS files. The 10.8 KB login HTML was rejected as source data and removed. No token or account was created, and no granule contents, cell quality or no-detection coverage is claimed. The next geolocation/product-quality implementation requires an authorized existing token or another independently documented open source; meanwhile the two genuine station pilots and archival analytics remain usable descriptive research.
