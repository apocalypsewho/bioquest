"""Darwin Core export of BIOQUEST field observations (CSV and Darwin Core Archive).

Two coordinate modes:

- ``exact``  — the observer's own data for their own use (e.g. the supplementary data of a manuscript,
  a museum catalogue). Only ever produced for observations the requester owns.
- ``public`` — ready to share or publish (GBIF IPT, a collaborative project): applies exactly the same
  rules as the API (``services.privacy``). Approximate records are snapped to the 0.1° cell centre,
  sensitive taxa to 0.2°, private records lose their coordinates. Every generalisation is declared in
  ``dataGeneralizations`` / ``informationWithheld`` and widens ``coordinateUncertaintyInMeters`` so the
  true point always lies inside the published uncertainty circle (as recommended by Chapman & Wieczorek,
  *Georeferencing Best Practices*, GBIF 2020).

DEMO observations are excluded unless explicitly requested, and are then flagged in every row.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from .privacy import APPROX_DEG, SENSITIVE_DEG, snap

DWC = "http://rs.tdwg.org/dwc/terms/"
DCT = "http://purl.org/dc/terms/"

TERMS: list[tuple[str, str]] = [
    ("occurrenceID", DWC), ("basisOfRecord", DWC), ("type", DCT), ("license", DCT), ("rightsHolder", DCT),
    ("modified", DCT), ("institutionCode", DWC), ("collectionCode", DWC), ("catalogNumber", DWC),
    ("recordedBy", DWC), ("individualCount", DWC), ("sex", DWC), ("occurrenceStatus", DWC),
    ("occurrenceRemarks", DWC), ("associatedMedia", DWC), ("associatedReferences", DWC),
    ("eventDate", DWC), ("year", DWC), ("month", DWC), ("day", DWC), ("habitat", DWC),
    ("samplingProtocol", DWC), ("eventRemarks", DWC), ("decimalLatitude", DWC), ("decimalLongitude", DWC),
    ("geodeticDatum", DWC), ("coordinateUncertaintyInMeters", DWC), ("minimumElevationInMeters", DWC),
    ("maximumElevationInMeters", DWC), ("georeferenceProtocol", DWC), ("informationWithheld", DWC),
    ("dataGeneralizations", DWC), ("scientificName", DWC), ("taxonID", DWC), ("kingdom", DWC),
    ("phylum", DWC), ("class", DWC), ("order", DWC), ("family", DWC), ("genus", DWC), ("taxonRank", DWC),
    ("vernacularName", DWC), ("identificationVerificationStatus", DWC), ("identifiedBy", DWC),
    ("identificationRemarks", DWC), ("dynamicProperties", DWC),
]
TERM_NAMES = [t for t, _ in TERMS]

LICENSES = {
    "cc0": ("CC0-1.0", "http://creativecommons.org/publicdomain/zero/1.0/legalcode",
            "Public Domain (CC0 1.0)"),
    "cc-by": ("CC-BY-4.0", "http://creativecommons.org/licenses/by/4.0/legalcode",
              "Creative Commons Attribution (CC-BY) 4.0"),
    "cc-by-nc": ("CC-BY-NC-4.0", "http://creativecommons.org/licenses/by-nc/4.0/legalcode",
                 "Creative Commons Attribution Non Commercial (CC-BY-NC) 4.0"),
}

ID_STATUS = {
    "needs_identification": "unverified (needs identification)",
    "user_identified": "identified by observer, not verified",
    "expert_verified": "verified by expert",
}

METERS_PER_DEG = 111_320.0


def cell_uncertainty_m(lat: float, cell_deg: float) -> float:
    """Radius (m) from the centre of a `cell_deg` square cell to its farthest corner at latitude `lat`."""
    half_lat = cell_deg / 2 * METERS_PER_DEG
    # widest east-west extent of the cell lies on its equatorward edge
    edge_lat = max(0.0, abs(lat) - cell_deg / 2)
    half_lon = cell_deg / 2 * METERS_PER_DEG * math.cos(math.radians(edge_lat))
    return math.ceil(math.hypot(half_lat, half_lon))


@dataclass
class ExportOptions:
    coordinates: str = "public"  # exact | public
    license: str = "cc-by-nc"
    base_url: str = ""  # public URL of the app, used for photo links
    rights_holder: str = ""


def _iso(d: dt.datetime | None) -> str:
    if d is None:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.isoformat(timespec="seconds")


def _round(x: float | None, nd: int = 6):
    return None if x is None else round(x, nd)


def observation_to_dwc(o, opts: ExportOptions, taxon: dict | None = None) -> dict:
    """Map one Observation (ORM object or anything with the same attributes) to Darwin Core terms.

    `taxon` is the cached taxon (``classification``, ``rank``, ``common_name``, ``is_sensitive``), if known.
    """
    taxon = taxon or {}
    cls = taxon.get("classification") or {}
    sensitive = bool(taxon.get("is_sensitive"))
    lat, lon, acc = o.lat, o.lon, o.accuracy_m
    withheld: list[str] = []
    generalised = ""
    protocol = "GNSS position recorded by the BIOQUEST app"
    alt = o.altitude_m

    if lat is not None and lon is not None and opts.coordinates != "exact":
        if o.coordinate_privacy == "private":
            lat = lon = acc = alt = None
            withheld.append("coordinates and elevation withheld at the observer's request (private record)")
        elif sensitive or o.coordinate_privacy == "approximate":
            cell = SENSITIVE_DEG if sensitive else APPROX_DEG
            slat, slon = snap(lat, lon, cell)
            acc = cell_uncertainty_m(slat, cell) + (o.accuracy_m or 0)
            lat, lon = slat, slon
            alt = None
            why = "sensitive taxon" if sensitive else "observer privacy setting"
            generalised = f"coordinates generalised to the centre of a {cell}° grid cell ({why}); elevation removed"
            withheld.append("precise location available from the observer on request")
            protocol += "; generalised by BIOQUEST privacy rules"

    when = o.observed_at
    remarks = (o.notes or "").strip()
    if o.is_demo:
        remarks = ("[DEMO DATA — fictitious record, do not use in analyses] " + remarks).strip()
    habitat = "; ".join(x for x in [(o.habitat or "").strip(), (o.microhabitat or "").strip()] if x)
    media = []
    if opts.base_url and o.coordinate_privacy != "private":
        media = [f"{opts.base_url.rstrip('/')}/api/photos/{p.id}" for p in (o.photos or [])]
    dyn = {k: v for k, v in {
        "temperatureInCelsius": o.temperature_c,
        "measurements": o.measurements or None,
        "morphology": o.morphology or None,
        "aiSuggestion": (o.ai_suggestion or {}).get("name") if isinstance(o.ai_suggestion, dict) else None,
        "missionId": o.mission_id, "expeditionId": o.expedition_id,
        "isDemo": bool(o.is_demo),
    }.items() if v not in (None, {}, "")}
    lic = LICENSES.get(opts.license, LICENSES["cc-by-nc"])
    name = (o.taxon_name or "").strip()
    return {
        "occurrenceID": f"urn:bioquest:observation:{o.client_uuid or o.id}",
        "basisOfRecord": "HumanObservation",
        "type": "Event",
        "license": lic[1],
        "rightsHolder": opts.rights_holder or (o.observer or ""),
        "modified": _iso(getattr(o, "created_at", None)),
        "institutionCode": "BIOQUEST",
        "collectionCode": "field-observations",
        "catalogNumber": str(o.id),
        "recordedBy": o.observer or "",
        "individualCount": o.individual_count,
        "sex": o.sex or "",
        "occurrenceStatus": "present",
        "occurrenceRemarks": remarks,
        "associatedMedia": " | ".join(media),
        "associatedReferences": (f"https://www.inaturalist.org/observations/{o.inat_observation_id}"
                                 if o.inat_observation_id else ""),
        "eventDate": _iso(when),
        "year": when.year if when else None,
        "month": when.month if when else None,
        "day": when.day if when else None,
        "habitat": habitat,
        "samplingProtocol": o.method or "",
        "eventRemarks": "",
        "decimalLatitude": _round(lat),
        "decimalLongitude": _round(lon),
        "geodeticDatum": "WGS84" if lat is not None else "",
        "coordinateUncertaintyInMeters": None if acc is None else math.ceil(acc),
        "minimumElevationInMeters": None if alt is None else round(alt),
        "maximumElevationInMeters": None if alt is None else round(alt),
        "georeferenceProtocol": protocol if lat is not None else "",
        "informationWithheld": "; ".join(withheld),
        "dataGeneralizations": generalised,
        "scientificName": name,
        "taxonID": o.taxon_key or "",
        "kingdom": cls.get("kingdom", ""),
        "phylum": cls.get("phylum", ""),
        "class": cls.get("class", ""),
        "order": cls.get("order", ""),
        "family": cls.get("family", ""),
        "genus": cls.get("genus", ""),
        "taxonRank": (taxon.get("rank") or "").lower(),
        "vernacularName": taxon.get("common_name") or "",
        "identificationVerificationStatus": ID_STATUS.get(o.id_status, o.id_status or ""),
        "identifiedBy": (o.observer or "") if name and o.id_status != "needs_identification" else "",
        "identificationRemarks": "" if name else "not yet identified",
        "dynamicProperties": json.dumps(dyn, ensure_ascii=False, sort_keys=True),
    }


# ------------------------------------------------------------------ serialisation
def _cell(v) -> str:
    if v is None:
        return ""
    return " ".join(str(v).split("\t")).replace("\r", " ").replace("\n", " ").strip()


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=TERM_NAMES, extrasaction="ignore", lineterminator="\r\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in TERM_NAMES})
    return buf.getvalue()


def to_occurrence_txt(rows: list[dict]) -> str:
    lines = ["\t".join(["id", *TERM_NAMES])]
    lines += ["\t".join(_cell(v) for v in [r["occurrenceID"], *(r.get(t) for t in TERM_NAMES)]) for r in rows]
    return "\n".join(lines) + "\n"


def meta_xml() -> str:
    fields = "\n".join(f'    <field index="{i}" term="{ns}{t}"/>' for i, (t, ns) in enumerate(TERMS, start=1))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<archive xmlns="http://rs.tdwg.org/dwc/text/" metadata="eml.xml">
  <core encoding="UTF-8" fieldsTerminatedBy="\\t" linesTerminatedBy="\\n" fieldsEnclosedBy="" ignoreHeaderLines="1" rowType="http://rs.tdwg.org/dwc/terms/Occurrence">
    <files>
      <location>occurrence.txt</location>
    </files>
    <id index="0"/>
{fields}
  </core>
</archive>
"""


def eml_xml(title: str, creator: str, rows: list[dict], opts: ExportOptions, package_id: str,
            description: str = "") -> str:
    lic = LICENSES.get(opts.license, LICENSES["cc-by-nc"])
    lats = [r["decimalLatitude"] for r in rows if r.get("decimalLatitude") is not None]
    lons = [r["decimalLongitude"] for r in rows if r.get("decimalLongitude") is not None]
    dates = sorted(r["eventDate"][:10] for r in rows if r.get("eventDate"))
    demo = any(json.loads(r.get("dynamicProperties") or "{}").get("isDemo") for r in rows)
    abstract = description or (f"Field observations recorded with BIOQUEST by {creator}. "
                               f"{len(rows)} occurrence records (basisOfRecord HumanObservation).")
    if opts.coordinates == "public":
        abstract += (" Coordinates follow the observers' privacy settings: generalised and private records are "
                     "declared in dataGeneralizations and informationWithheld.")
    if demo:
        abstract += " WARNING: includes fictitious DEMO records; do not publish to GBIF."
    geo = ""
    if lats:
        geo = f"""
      <geographicCoverage>
        <geographicDescription>Bounding box of the exported records</geographicDescription>
        <boundingCoordinates>
          <westBoundingCoordinate>{min(lons)}</westBoundingCoordinate>
          <eastBoundingCoordinate>{max(lons)}</eastBoundingCoordinate>
          <northBoundingCoordinate>{max(lats)}</northBoundingCoordinate>
          <southBoundingCoordinate>{min(lats)}</southBoundingCoordinate>
        </boundingCoordinates>
      </geographicCoverage>"""
    temporal = ""
    if dates:
        temporal = f"""
      <temporalCoverage>
        <rangeOfDates>
          <beginDate><calendarDate>{dates[0]}</calendarDate></beginDate>
          <endDate><calendarDate>{dates[-1]}</calendarDate></endDate>
        </rangeOfDates>
      </temporalCoverage>"""
    coverage = f"\n    <coverage>{geo}{temporal}\n    </coverage>" if (geo or temporal) else ""
    party = f"<individualName><surName>{escape(creator)}</surName></individualName>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<eml:eml xmlns:eml="eml://ecoinformatics.org/eml-2.1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="eml://ecoinformatics.org/eml-2.1.1 http://rs.gbif.org/schema/eml-gbif-profile/1.2/eml.xsd"
  packageId={quoteattr(package_id)} system="BIOQUEST" scope="system" xml:lang="en">
  <dataset>
    <title xml:lang="en">{escape(title)}</title>
    <creator>{party}</creator>
    <metadataProvider>{party}</metadataProvider>
    <pubDate>{dt.date.today().isoformat()}</pubDate>
    <language>en</language>
    <abstract><para>{escape(abstract)}</para></abstract>
    <intellectualRights><para>This work is licensed under a <ulink url={quoteattr(lic[1])}><citetitle>{escape(lic[2])}</citetitle></ulink>.</para></intellectualRights>{coverage}
    <contact>{party}</contact>
  </dataset>
</eml:eml>
"""


def dwca_zip(rows: list[dict], eml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("meta.xml", meta_xml())
        z.writestr("eml.xml", eml)
        z.writestr("occurrence.txt", to_occurrence_txt(rows))
    return buf.getvalue()
