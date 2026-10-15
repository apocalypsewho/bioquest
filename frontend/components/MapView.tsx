"use client";
import maplibregl, { GeoJSONSource, ImageSource, Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { gridToImage, GridJSON, RAMPS } from "@/lib/raster";

export type Occ = { uid: string; lat: number | null; lon: number | null; source: string; qc_status: string;
  scientific_name?: string; event_date?: string | null; url?: string | null; qc_reasons?: string[] };

export type MapLayers = {
  occurrences?: Occ[];
  heatmap?: boolean;
  raster?: { grid: GridJSON; ramp: keyof typeof RAMPS; opacity?: number; domain?: [number, number] } | null;
  zone?: { polygon: number[][]; center: { lat: number; lon: number } } | null;
  signals?: { lat: number; lon: number; score?: number }[];
  route?: number[][];
  points?: { lat: number; lon: number; label?: string }[];
  you?: { lat: number; lon: number; demo?: boolean } | null;
};

const STYLE_URL = process.env.NEXT_PUBLIC_MAP_STYLE_URL;
// Default basemap: CARTO "Dark Matter" raster tiles (data © OpenStreetMap contributors). Free for
// non-commercial / low-volume use — see https://carto.com/basemaps and README for alternatives.
const RASTER_TILES = process.env.NEXT_PUBLIC_BASEMAP_TILES ||
  "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png";
const ATTRIB = process.env.NEXT_PUBLIC_BASEMAP_ATTRIBUTION ||
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>';

const defaultStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: { base: { type: "raster", tiles: [RASTER_TILES], tileSize: 256, attribution: ATTRIB } },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#040706" } },
    { id: "base", type: "raster", source: "base", paint: { "raster-opacity": 0.85, "raster-saturation": -0.6,
      "raster-hue-rotate": 120, "raster-brightness-max": 0.75 } },
  ],
};

const SRC_COLOR: maplibregl.ExpressionSpecification = ["match", ["get", "source"],
  "inaturalist", "#3dffc5", "gbif", "#38d9ff", "demo", "#ffb547", "user", "#ffffff", "#e9f2ee"];

const EMPTY = { type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection;

export default function MapView({ center, zoom = 9, layers, onClick, fitTo, className = "", interactive = true }: {
  center: { lat: number; lon: number };
  zoom?: number;
  layers: MapLayers;
  onClick?: (lat: number, lon: number, map: MLMap) => void;
  fitTo?: [number, number, number, number] | null;
  className?: string;
  interactive?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [loaded, setLoaded] = useState(false);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;

  useEffect(() => {
    if (!ref.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      style: STYLE_URL || defaultStyle,
      center: [center.lon, center.lat],
      zoom,
      attributionControl: { compact: true },
      interactive,
    });
    mapRef.current = map;
    if (interactive) {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
      map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), "bottom-right");
      map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    }
    map.on("load", () => {
      map.addSource("raster", { type: "image", url: transparentPng, coordinates: [[0, 1], [1, 1], [1, 0], [0, 0]] });
      map.addLayer({ id: "raster", type: "raster", source: "raster", paint: { "raster-opacity": 0, "raster-fade-duration": 300,
        "raster-resampling": "nearest" } });
      for (const id of ["occ", "zone", "signals", "route", "points", "you"]) map.addSource(id, { type: "geojson", data: EMPTY });
      map.addLayer({ id: "occ-heat", type: "heatmap", source: "occ", layout: { visibility: "none" },
        paint: { "heatmap-radius": 22, "heatmap-intensity": 0.9, "heatmap-opacity": 0.75,
          "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.3, "#0d4b40",
            0.6, "#1fa98a", 0.9, "#3dffc5", 1, "#eafff8"] } });
      map.addLayer({ id: "zone-fill", type: "fill", source: "zone", paint: { "fill-color": "#3dffc5", "fill-opacity": 0.08 } });
      map.addLayer({ id: "zone-line", type: "line", source: "zone", paint: { "line-color": "#3dffc5", "line-width": 1.5,
        "line-dasharray": [2, 2] } });
      map.addLayer({ id: "signals", type: "circle", source: "signals", paint: { "circle-radius": 3, "circle-color": "#3dffc5",
        "circle-opacity": 0.55, "circle-blur": 0.6 } });
      map.addLayer({ id: "route", type: "line", source: "route", paint: { "line-color": "#38d9ff", "line-width": 2.5 } });
      map.addLayer({ id: "occ", type: "circle", source: "occ", paint: {
        "circle-radius": ["case", ["==", ["get", "qc_status"], "EXCLUDED"], 3.5, 4.5],
        "circle-color": ["case", ["==", ["get", "qc_status"], "EXCLUDED"], "rgba(0,0,0,0)", SRC_COLOR],
        "circle-stroke-color": ["case", ["==", ["get", "qc_status"], "VALID"], "#040706",
          ["==", ["get", "qc_status"], "QUESTIONABLE"], "#ffb547", "#ff6370"],
        "circle-stroke-width": ["case", ["==", ["get", "qc_status"], "VALID"], 0.8, 1.6],
        "circle-opacity": 0.95 } });
      map.addLayer({ id: "points", type: "circle", source: "points", paint: { "circle-radius": 6, "circle-color": "#ffffff",
        "circle-stroke-color": "#3dffc5", "circle-stroke-width": 2 } });
      map.addLayer({ id: "you", type: "circle", source: "you", paint: { "circle-radius": 7, "circle-color": "#38d9ff",
        "circle-stroke-color": "#040706", "circle-stroke-width": 3 } });

      map.on("click", "occ", (e) => {
        const p = e.features?.[0]?.properties as Record<string, string> | undefined;
        if (!p) return;
        const reasons = JSON.parse(p.qc_reasons || "[]") as string[];
        new maplibregl.Popup({ maxWidth: "280px" })
          .setLngLat(e.lngLat)
          .setHTML(`<div style="line-height:1.5"><b>${p.scientific_name ?? ""}</b><br/>source: ${p.source}<br/>` +
            `date: ${p.event_date ?? "—"}<br/>QC: <b>${p.qc_status}</b>${reasons.length ? `<br/><span style="color:#8fa39b">${reasons.join("<br/>")}</span>` : ""}` +
            `${p.url ? `<br/><a href="${p.url}" target="_blank" rel="noreferrer" style="color:#3dffc5">open record ↗</a>` : ""}</div>`)
          .addTo(map);
      });
      map.on("click", (e) => {
        if (map.queryRenderedFeatures(e.point, { layers: ["occ"] }).length) return;
        clickRef.current?.(e.lngLat.lat, e.lngLat.lng, map);
      });
      setLoaded(true);
    });
    return () => map.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const set = (id: string, fc: GeoJSON.FeatureCollection) => (map.getSource(id) as GeoJSONSource).setData(fc);
    set("occ", fc((layers.occurrences || []).filter((o) => o.lat != null).map((o) => point(o.lon!, o.lat!, {
      ...o, qc_reasons: JSON.stringify(o.qc_reasons || []) }))));
    map.setLayoutProperty("occ-heat", "visibility", layers.heatmap ? "visible" : "none");
    set("zone", fc(layers.zone ? [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [layers.zone.polygon] } }] : []));
    set("signals", fc((layers.signals || []).map((s) => point(s.lon, s.lat, { score: s.score ?? 0 }))));
    set("route", fc(layers.route && layers.route.length > 1 ? [{ type: "Feature", properties: {},
      geometry: { type: "LineString", coordinates: layers.route.map((p) => [p[0], p[1]]) } }] : []));
    set("points", fc((layers.points || []).map((p) => point(p.lon, p.lat, { label: p.label ?? "" }))));
    set("you", fc(layers.you ? [point(layers.you.lon, layers.you.lat, {})] : []));
    const src = map.getSource("raster") as ImageSource;
    if (layers.raster) {
      const im = gridToImage(layers.raster.grid, layers.raster.ramp, layers.raster.domain);
      src.updateImage({ url: im.url, coordinates: im.coordinates });
      map.setPaintProperty("raster", "raster-opacity", layers.raster.opacity ?? 0.85);
    } else {
      map.setPaintProperty("raster", "raster-opacity", 0);
    }
  }, [layers, loaded]);

  useEffect(() => {
    if (!fitTo || !mapRef.current || !loaded) return;
    mapRef.current.fitBounds([[fitTo[0], fitTo[1]], [fitTo[2], fitTo[3]]], { padding: 60, duration: 1200, maxZoom: 13 });
  }, [fitTo, loaded]);

  useEffect(() => {
    if (!mapRef.current || !loaded) return;
    mapRef.current.easeTo({ center: [center.lon, center.lat], duration: 900 });
  }, [center.lat, center.lon, loaded]);

  return <div ref={ref} className={`h-full w-full ${className}`} />;
}

function point(lon: number, lat: number, properties: Record<string, unknown>): GeoJSON.Feature {
  return { type: "Feature", properties, geometry: { type: "Point", coordinates: [lon, lat] } };
}
function fc(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features };
}
const transparentPng =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";
