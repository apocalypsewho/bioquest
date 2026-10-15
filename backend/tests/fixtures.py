"""Minimal response bodies shaped like the documented iNaturalist v1 and GBIF v1 responses.

They are TEST FIXTURES (not real records): they only exercise the parsing code paths.
"""

INAT_AUTOCOMPLETE = {
    "total_results": 1, "page": 1, "per_page": 10,
    "results": [{
        "id": 900001, "name": "Testgenus testus", "rank": "species", "preferred_common_name": "Test sun-spider",
        "observations_count": 3, "ancestor_ids": [48460, 1, 900000, 900001], "iconic_taxon_name": "Arachnida",
        "default_photo": {"medium_url": "https://example.org/photo/medium.jpg", "attribution": "(c) tester"},
    }],
}

INAT_TAXON = {"total_results": 1, "results": [{
    **INAT_AUTOCOMPLETE["results"][0],
    "ancestors": [{"id": 1, "rank": "kingdom", "name": "Animalia"}, {"id": 900000, "rank": "genus", "name": "Testgenus"}],
}]}


def inat_obs(i, lat, lon, **kw):
    o = {
        "id": i, "uri": f"https://www.inaturalist.org/observations/{i}",
        "geojson": {"type": "Point", "coordinates": [lon, lat]}, "location": f"{lat},{lon}",
        "positional_accuracy": 20, "public_positional_accuracy": 20, "observed_on": "2023-05-01",
        "observed_on_details": {"year": 2023}, "quality_grade": "research",
        "taxon": {"id": 900001, "name": "Testgenus testus", "rank": "species", "ancestor_ids": [48460, 1, 900000, 900001]},
        "user": {"id": 5, "login": "tester"}, "photos": [{"url": "https://example.org/p/square.jpg"}],
        "obscured": False, "geoprivacy": None, "taxon_geoprivacy": None, "captive": False,
    }
    o.update(kw)
    return o


INAT_OBSERVATIONS = {"total_results": 3, "page": 1, "per_page": 200, "results": [
    inat_obs(101, -12.1234, -75.2345),
    inat_obs(102, -12.2234, -75.3345, quality_grade="needs_id"),
    inat_obs(103, -12.3234, -75.4345, captive=True, quality_grade="casual"),
]}

GBIF_SUGGEST = [{"key": 7000001, "scientificName": "Testgenus testus Author, 1900", "canonicalName": "Testgenus testus",
                 "rank": "SPECIES", "kingdom": "Animalia", "phylum": "Arthropoda", "class": "Arachnida",
                 "order": "Solifugae", "family": "Testidae", "genus": "Testgenus", "species": "Testgenus testus",
                 "status": "ACCEPTED"}]

GBIF_MATCH = {"usageKey": 7000001, "scientificName": "Testgenus testus Author, 1900", "canonicalName": "Testgenus testus",
              "rank": "SPECIES", "matchType": "EXACT", "confidence": 99, "kingdom": "Animalia", "genus": "Testgenus"}


def gbif_occ(key, lat, lon, **kw):
    o = {"key": key, "decimalLatitude": lat, "decimalLongitude": lon, "coordinateUncertaintyInMeters": 50,
         "eventDate": "2019-02-03T00:00:00", "year": 2019, "basisOfRecord": "PRESERVED_SPECIMEN",
         "institutionCode": "MUSM", "datasetKey": "d-1", "countryCode": "PE", "species": "Testgenus testus",
         "taxonRank": "SPECIES", "speciesKey": 7000001, "genusKey": 7000000, "taxonKey": 7000001, "issues": []}
    o.update(kw)
    return o


GBIF_OCCURRENCES = {"offset": 0, "limit": 300, "endOfRecords": True, "count": 4, "results": [
    gbif_occ(1, -12.5123, -75.6234),
    gbif_occ(2, 0.0, 0.0, issues=["ZERO_COORDINATE"]),
    # GBIF copy of iNaturalist observation 101 → must be flagged as duplicate
    gbif_occ(3, -12.1234, -75.2345, datasetKey="50c9509d-22c7-4a22-a47d-8c48425ef4a7", catalogNumber="101",
             basisOfRecord="HUMAN_OBSERVATION"),
    gbif_occ(4, -12.6, -75.7, issues=["COUNTRY_COORDINATE_MISMATCH"]),
]}
GBIF_NO_COORD = {"offset": 0, "limit": 0, "endOfRecords": False, "count": 7, "results": []}
GBIF_FACETS = {"count": 11, "results": [], "facets": [
    {"field": "COUNTRY", "counts": [{"name": "PE", "count": 10}, {"name": "BO", "count": 1}]},
    {"field": "YEAR", "counts": [{"name": "2019", "count": 4}, {"name": "1987", "count": 1}]},
]}
