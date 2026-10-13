"""Offline, source-aware historical thermal-signal analysis from verified FIRMS SQLite.

This is statistical analysis of archived detections, not wildfire prediction.
Recorded GitHub scan requests are *not* satellite overpass opportunities.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
from html import escape
import json
import math
from pathlib import Path
import sqlite3
from statistics import median
from urllib.parse import quote

from .collect import FIRMS_SOURCES
from .history import _timestamp
from .region_diagnostics import distance_km

WINDOWS = (24, 48, 72, 168, 336)
N_BINS = 12
MAX_SCANS = 10_000
MAX_PIXELS = 250_000
MAX_SOURCE_PROOFS = 128
SOURCES = tuple(FIRMS_SOURCES)
ROOT = Path(__file__).resolve().parents[1]


def _valid_coordinate(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(_timestamp(value))


def _hours(start: datetime, moment: datetime) -> float:
    return (moment - start).total_seconds() / 3600


def _median_mad(values: list[int]) -> tuple[float, float]:
    midpoint = median(values)
    return midpoint, median(abs(x - midpoint) for x in values)


def _slope(counts: list[int], width_hours: float) -> float:
    return round(median((counts[j] - counts[i]) / ((j-i)*width_hours)
                        for i in range(len(counts)) for j in range(i+1,len(counts))), 6)


def _read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def analyze_historical_signals(
    db_path: Path | str, *, at: str, hours: int = 72,
    latitude: float, longitude: float, radius_km: float = 100,
    source: str = "all"
) -> dict:
    """Same UTC window for scan/source audits and original pixel event-time bins.

    The requested decision time also gates *first capture*. An observed pixel
    received after the decision cutoff must not leak backward through history.
    """
    if (type(hours) is not int or hours not in WINDOWS or
        not _valid_coordinate(latitude,-90,90) or
        not _valid_coordinate(longitude,-180,180) or
        not _valid_coordinate(radius_km,0.01,250) or
        source not in ("all",*SOURCES)):
        raise ValueError("valid global circle, FIRMS source and supported UTC window required")
    decision = _utc(at)
    start = decision - timedelta(hours=hours)
    width = timedelta(hours=hours/N_BINS)
    selected = SOURCES if source=="all" else (source,)
    def bucket(moment: datetime) -> int:
        return max(0, min(N_BINS-1, int((moment-start)/width)))
    bins = [{
        "index":i,
        "from":(start+i*width).isoformat(),
        "to":(start+(i+1)*width).isoformat(),
        "observed_cell_hours":0,
        "distinct_cells":0,
        "unique_raw_pixels":0,
        "first_captured_here":0,
        "late_first_captures":0,
        "sensor_cell_hour_memberships":{key:0 for key in selected},
        "collection_receipts":0,
        "source_scan_counts":{key:{"complete":0,"failed":0,"deferred":0} for key in selected},
        "collection_evidence":"no_receipt",
        "observation_opportunities_verified":False
    } for i in range(N_BINS)]
    cutoff = decision.isoformat()
    beginning = start.isoformat()
    with closing(_read_only(Path(db_path))) as db:
        # Limit + 1: reject overflow rather than output an apparently complete
        # but silently downsampled historical scientific estimate.
        scans = db.execute("""
            SELECT scan_at,captured_at,snapshot_key,receipt_sha256,source_states_json
            FROM pixel_scans
            WHERE scan_at >= ? AND scan_at < ?
              AND captured_at <= ?
            ORDER BY scan_at ASC LIMIT ?
        """, (beginning,cutoff,cutoff,MAX_SCANS+1)).fetchall()
        if len(scans)>MAX_SCANS:
            raise ValueError("historical scan population exceeds analysis budget")
        pixels = db.execute("""
            SELECT provider,observed_at,first_captured_at,latitude,longitude
            FROM pixel_observations
            WHERE observed_at >= ? AND observed_at < ?
              AND first_captured_at <= ?
              AND provider IN (?,?)
            ORDER BY observed_at,source_record_id LIMIT ?
        """, (beginning,cutoff,cutoff,*SOURCES,MAX_PIXELS+1)).fetchall()
        if len(pixels)>MAX_PIXELS:
            raise ValueError("historical raw pixel population exceeds analysis budget")

    references=[]
    all_reference_hashes=[]
    scan_sources=Counter()
    for scan in scans:
        scan_date=_utc(scan["scan_at"])
        idx=bucket(scan_date)
        b=bins[idx]
        states=json.loads(scan["source_states_json"])
        if not isinstance(states,dict) or set(states)!=set(SOURCES) or any(
            status not in {"complete","failed","deferred"} for status in states.values()
        ):
            raise ValueError("archived source scan states invalid")
        b["collection_receipts"]+=1
        for key in selected:
            b["source_scan_counts"][key][states[key]]+=1
            scan_sources[key+":"+states[key]]+=1
        digest=scan["receipt_sha256"]
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("source scan checksum unavailable")
        all_reference_hashes.append(digest)
        if len(references)<MAX_SOURCE_PROOFS:
            references.append({"scan_at":scan["scan_at"],
                "captured_at":scan["captured_at"],"receipt_sha256":digest,
                "snapshot_key":scan["snapshot_key"]})

    # Store grouped *original* raw-pixel evidence per bin, not just counts.
    sensor_groups = [defaultdict(set) for _ in range(N_BINS)]
    bin_cells = [set() for _ in range(N_BINS)]
    group_hours = [set() for _ in range(N_BINS)]
    unique_sensor_pixels=Counter()
    late_pixels=0
    accepted=0
    temporal_latency=[]
    for pixel in pixels:
        provider=pixel["provider"]
        if provider not in selected:
            continue
        lat,lon=pixel["latitude"],pixel["longitude"]
        if not (_valid_coordinate(lat,-90,90) and _valid_coordinate(lon,-180,180)):
            raise ValueError("archived pixel coordinate outside geographic contract")
        if distance_km(latitude,longitude,lat,lon)>radius_km:
            continue
        observed,received=_utc(pixel["observed_at"]),_utc(pixel["first_captured_at"])
        if received < observed or received > decision:
            raise ValueError("archived pixel capture timing contradictory")
        # Pixel provenance has already been verified by pixel_history import.
        # Normalize longitude to avoid splitting 180°/-180° in one cell.
        normalized_lon=(lon+180)%360-180
        cell=(math.floor(lat*20),math.floor(normalized_lon*20))
        hour=observed.replace(minute=0,second=0,microsecond=0)
        group=(cell,hour.isoformat())
        idx=bucket(observed)
        bins[idx]["unique_raw_pixels"]+=1
        bin_cells[idx].add(cell)
        group_hours[idx].add(group)
        sensor_groups[idx][provider].add(group)
        accepted+=1
        unique_sensor_pixels[provider]+=1
        if start <= received < decision:
            capture_bin=bins[bucket(received)]
            capture_bin["first_captured_here"]+=1
            if bucket(received)>idx:
                capture_bin["late_first_captures"]+=1
                late_pixels+=1
        temporal_latency.append(_hours(observed,received))

    missing=0
    all_complete=0
    any_failed=0
    for i,b in enumerate(bins):
        b["observed_cell_hours"]=len(group_hours[i])
        b["distinct_cells"]=len(bin_cells[i])
        for provider in selected:
            b["sensor_cell_hour_memberships"][provider]=len(sensor_groups[i].get(provider,set()))
        if not b["collection_receipts"]:
            missing+=1
            b["collection_evidence"]="no_receipt"
        elif all(b["source_scan_counts"][provider]["complete"]>0 for provider in selected):
            all_complete+=1
            b["collection_evidence"]="all_selected_source_requests_completed_at_least_once"
        else:
            b["collection_evidence"]="no_complete_receipt_for_one_or_more_selected_sources"
            any_failed+=1

    counts=[b["observed_cell_hours"] for b in bins]
    known_bins=all_complete==N_BINS
    med,mad=_median_mad(counts)
    trend = _slope(counts,hours/N_BINS) if known_bins else None
    half1=sum(counts[:N_BINS//2])
    half2=sum(counts[N_BINS//2:])
    pair_counts=Counter()
    # Co-membership is a property of the same spatial/hour aggregation,
    # not independent agreement on an actual physical fire.
    for i in range(N_BINS):
        both=set.intersection(*[sensor_groups[i].get(s,set()) for s in selected]) if len(selected)>1 else set()
        pair_counts["co_observed_cell_hours"]+=len(both)
    latest=None
    for pixel in pixels:
        if pixel["provider"] not in selected:
            continue
        if (distance_km(latitude,longitude,pixel["latitude"],pixel["longitude"])<=radius_km and
                (latest is None or pixel["observed_at"]>latest)):
            latest=pixel["observed_at"]
    return {
        "schema_version":1,
        "kind":"archived_firms_scan_aware_regional_signal_analysis",
        "research_maturity":"experimental_descriptive_historical_not_fire_model",
        "source_provenance":"verified_original_FIRMS_release_pixel_sqlite",
        "decision_at":cutoff,
        "window":{"from":beginning,"to":cutoff,"hours":hours,
                  "bins":N_BINS,"bucket_hours":hours/N_BINS,
                  "boundary":"from_inclusive_to_exclusive"},
        "circle":{"latitude":latitude,"longitude":longitude,
                  "radius_km":radius_km,"geometry":"geodesic"},
        "selected_sources":list(selected),
        "scan_receipts":len(scans),
        "scan_source_states":dict(sorted(scan_sources.items())),
        "provenance_receipts":references,
        "provenance_receipt_count_excluded_from_list":max(0,len(scans)-len(references)),
        "provenance_receipts_sha256":hashlib.sha256(
            "\n".join(all_reference_hashes).encode()).hexdigest(),
        "bin_quality":{
            "bins_with_no_receipt":missing,
            "bins_with_all_selected_sources_complete_receipts":all_complete,
            "bins_without_a_complete_receipt_for_every_selected_source":any_failed,
            "satellite_overpass_opportunities_known":False,
            "region_fully_observed":False,
            "trend_descriptive_only_available":known_bins,
            "comparable_satellite_acquisition_opportunities_verified":False,
        },
        "bins":bins,
        "summary":{
            "unique_raw_pixel_observations":accepted,
            "raw_pixels_by_sensor":dict(sorted(unique_sensor_pixels.items())),
            "distinct_candidate_cell_hours":sum(counts),
            "distinct_cells_across_window":len(set().union(*bin_cells)),
            "multi_sensor_cell_hours":pair_counts["co_observed_cell_hours"],
            "latest_original_observed_at":latest,
            "delayed_captures_in_later_observation_bin":late_pixels,
            "capture_lag_hours_median":round(median(temporal_latency),3) if temporal_latency else None,
            "median_bin_cell_hours":med if known_bins else None,
            "mad_bin_cell_hours":mad if known_bins else None,
            "theil_sen_cell_hours_per_hour":trend,
            "later_minus_earlier_cell_hours":half2-half1 if known_bins else None,
            "later_to_earlier_cell_hours_ratio":round(half2/half1,3) if known_bins and half1 else None,
        },
        "verified_fire_count":None,
        "verified_nonfire_count":None,
        "wildfire_probability":None,
        "fire_growth_rate":None,
        "estimated_satellite_overpass_exposure":None,
        "observation_adjusted_wildfire_frequency":None,
        "independent_fire_outcomes":None,
        "warnings":[
            "Every pixel was previously checksum-verified against its original historical release source fields; this is still a SATELLITE THERMAL DETECTION, NOT a validated wildfire.",
            "A successful scan receipt proves a collection request, not a satellite pass, cloud-free view, or uniformly exposed location.",
            "No scan receipt in a bin is MISSING EVIDENCE, not zero fire observations. The raw candidate count can include pixels first received in a later bin.",
            "Descriptive temporal trend is withheld unless every bin has at least one complete receipt for every selected source. Even then it is not an exposure-adjusted risk trend.",
            "Source acquisition coverage and negative wildfire labels are unverified. No p-value, calibrated ignition/spread probability, or burned-area estimate is available.",
            "Stored first-captured time reflects the earliest imported source receipt, not guaranteed earlier external visibility."
        ]
    }


def render_html(report: dict) -> str:
    """A standalone offline statistical report; no JS, CDNs, tracking or APIs."""
    bins=report["bins"]
    summary=report["summary"]
    quality=report["bin_quality"]
    maxval=max(1,*[b["observed_cell_hours"] for b in bins])
    def e(value):return escape(str(value),quote=True)
    def fmt(value):return "Unavailable" if value is None else e(value)
    rows=[]
    for b in bins:
        count=b["observed_cell_hours"]
        perc=round(100*count/maxval,1)
        status=b["collection_evidence"]
        levels="".join("<span class='bar' style='width:"+str(perc)+"%'></span>")
        label=e(b["from"][5:16].replace("T"," "))+" UTC"
        rows.append("<tr><th scope='row'>"+label+"</th><td>"+e(count)+
            "</td><td>"+e(b["distinct_cells"])+"</td><td>"+e(b["unique_raw_pixels"])+
            "</td><td>"+e(b["collection_receipts"])+"</td><td>"+e(status)+
            "</td><td><div class='bar-track' aria-hidden='true'>"+levels+"</div></td></tr>")
    cards=[
        ("Distinct thermal cell-hours",summary["distinct_candidate_cell_hours"]),
        ("Unique raw detections",summary["unique_raw_pixel_observations"]),
        ("Completed-source bins",str(quality["bins_with_all_selected_sources_complete_receipts"])+"/12"),
        ("No-scan bins",quality["bins_with_no_receipt"]),
        ("Median cell-hours/bin",summary["median_bin_cell_hours"]),
        ("MAD cell-hours/bin",summary["mad_bin_cell_hours"]),
        ("Theil-Sen cell-hours/hour",summary["theil_sen_cell_hours_per_hour"]),
        ("Late first-captures",summary["delayed_captures_in_later_observation_bin"]),
    ]
    tiles="".join("<div class='tile'><span>"+e(k)+"</span><strong>"+fmt(v)+"</strong></div>"
                  for k,v in cards)
    warnings="".join("<li>"+e(x)+"</li>" for x in report["warnings"])
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FIRMS Historical Statistical Signal Analysis</title>
<style>
:root{color-scheme:dark;font:15px system-ui,sans-serif;background:#0e1b25;color:#e7f0f3}
body{max-width:1160px;margin:24px auto;padding:0 18px;line-height:1.5}
h1{font-size:1.75rem}h2{font-size:1.3rem;margin-top:2rem}
.subtitle{color:#bbced9}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.tile{border:1px solid #335464;border-radius:8px;padding:12px;display:flex;flex-direction:column;gap:8px}
.tile span{font-size:.86rem;color:#c5d7df}.tile strong{font-size:1.35rem;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:840px}
th,td{border-bottom:1px solid #325160;text-align:left;padding:9px 7px;font-size:.86rem}
th[scope=row]{white-space:nowrap} .bar-track{width:140px;background:#284451;height:14px}
.bar{display:block;height:100%;background:#8dcbd5}li{margin:8px 0}
small{color:#bdd0da}code{overflow-wrap:anywhere}
</style></head><body><main>
<h1>FIRMS historical statistical analysis</h1>
<p class="subtitle">Original archived thermal detections • observational, not confirmed wildfire or fire risk</p>
<p>UTC decision: <strong>""" + e(report["decision_at"]) +
        "</strong> · Window: "+e(report["window"]["hours"])+" h · Sources: "+
        e(", ".join(report["selected_sources"]))+"</p><p>Circle: "+
        e(report["circle"]["latitude"])+", "+e(report["circle"]["longitude"])+
        " / "+e(report["circle"]["radius_km"])+" km</p><section aria-label='Statistics'><div class='tiles'>"+
        tiles+"</div></section><section><h2>Scan and acquisition evidence</h2><p>"+
        e(quality["bins_with_no_receipt"])+" of 12 bins lacked downloaded scan receipts. "+
        "A complete collection request <strong>does not</strong> establish a verified satellite overpass. "+
        "Temporal trend is withheld when any selected source lacks a completed receipt in a bin.</p></section>"+
        "<section><h2>Time-binned data (UTC)</h2><div class='scroll'><table><thead><tr>"+
        "<th>Bin start</th><th>Cell-hours</th><th>Cells</th><th>Raw pixels</th>"+
        "<th>Scan receipts</th><th>Collection evidence</th><th>Observed cell-hours (relative scale)</th>"+
        "</tr></thead><tbody>"+"".join(rows)+"</tbody></table></div></section>"+
        "<section><h2>Interpretation limits</h2><ul>"+warnings+
        "</ul></section><footer><small>Local generated output. No external resources or network requests.</small></footer>"+
        "</main></body></html>\n")


def main() -> None:
    parser=argparse.ArgumentParser(description="Historical source-aware thermal-signal statistical research (offline)")
    parser.add_argument("--pixel-db",required=True,type=Path)
    parser.add_argument("--at",required=True,help="UTC-aware as-of cutoff")
    parser.add_argument("--hours",type=int,choices=WINDOWS,default=72)
    parser.add_argument("--latitude",type=float,required=True)
    parser.add_argument("--longitude",type=float,required=True)
    parser.add_argument("--radius-km",type=float,required=True)
    parser.add_argument("--source",choices=("all",*SOURCES),default="all")
    parser.add_argument("--json",type=Path)
    parser.add_argument("--html",type=Path)
    args=parser.parse_args()
    report=analyze_historical_signals(args.pixel_db,at=args.at,hours=args.hours,
        latitude=args.latitude,longitude=args.longitude,radius_km=args.radius_km,
        source=args.source)
    for target in (args.json,args.html):
        if target is not None:
            if target.is_symlink() or target.exists() or target.resolve()==args.pixel_db.resolve():
                parser.error("outputs must be new files and cannot overwrite source database")
            if not target.parent.is_dir():
                parser.error("output parent directory must exist")
    if args.json and args.html and args.json.resolve()==args.html.resolve():
        parser.error("HTML and JSON must not overwrite each other")
    if args.json:
        with args.json.open("x",encoding="utf-8") as stream:
            stream.write(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    if args.html:
        with args.html.open("x",encoding="utf-8") as stream:
            stream.write(render_html(report))
    print(json.dumps({"status":"complete","scan_receipts":report["scan_receipts"],
          "raw_pixels":report["summary"]["unique_raw_pixel_observations"],
          "completed_receipt_bins":report["bin_quality"]["bins_with_all_selected_sources_complete_receipts"],
          "temporal_trend_available":report["bin_quality"]["trend_descriptive_only_available"],
          "forecast_generated":False},sort_keys=True))


if __name__=="__main__":
    main()
