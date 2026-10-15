/** Render a backend grid (lat/lon regular, row 0 = north) to a PNG data URL in Web-Mercator rows,
 *  so the MapLibre image source lines up correctly even over large latitude ranges.
 *  Only colour mapping happens here — all computation is done by the backend. */

export type GridJSON = { bbox: [number, number, number, number]; res: number; width: number; height: number;
  values: (number | null)[] };

type Stop = [number, [number, number, number, number]];

export const RAMPS: Record<string, Stop[]> = {
  // environmental suitability: transparent → deep teal → signal green → white
  suitability: [
    [0, [6, 30, 28, 0]],
    [0.25, [10, 70, 64, 90]],
    [0.5, [20, 140, 120, 150]],
    [0.75, [61, 255, 197, 200]],
    [1, [235, 255, 248, 235]],
  ],
  gap: [
    [0, [56, 217, 255, 0]],
    [0.4, [90, 80, 200, 70]],
    [0.7, [167, 139, 250, 140]],
    [1, [255, 181, 71, 190]],
  ],
  agreement: [
    [0, [0, 0, 0, 0]],
    [0.34, [56, 120, 140, 90]],
    [0.67, [56, 217, 255, 150]],
    [1, [61, 255, 197, 210]],
  ],
  extrapolation: [
    [0, [0, 0, 0, 0]],
    [1, [255, 99, 112, 150]],
  ],
};

function colour(v: number, ramp: Stop[]) {
  if (v <= ramp[0][0]) return ramp[0][1];
  for (let i = 1; i < ramp.length; i++) {
    const [t1, c1] = ramp[i];
    const [t0, c0] = ramp[i - 1];
    if (v <= t1) {
      const f = (v - t0) / (t1 - t0);
      return c0.map((c, k) => c + (c1[k] - c) * f) as [number, number, number, number];
    }
  }
  return ramp[ramp.length - 1][1];
}

const mercY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const invMercY = (y: number) => (360 / Math.PI) * Math.atan(Math.exp(y)) - 90;

export function gridToImage(g: GridJSON, ramp: keyof typeof RAMPS, domain: [number, number] = [0, 1]) {
  const [minlon, minlat, maxlon, maxlat] = g.bbox;
  const outH = Math.min(Math.max(g.height * 2, 64), 1200);
  const canvas = document.createElement("canvas");
  canvas.width = g.width;
  canvas.height = outH;
  const ctx = canvas.getContext("2d")!;
  const img = ctx.createImageData(g.width, outH);
  const y0 = mercY(Math.min(maxlat, 85)), y1 = mercY(Math.max(minlat, -85));
  for (let r = 0; r < outH; r++) {
    const lat = invMercY(y0 + ((r + 0.5) / outH) * (y1 - y0));
    const row = Math.min(g.height - 1, Math.max(0, Math.floor((maxlat - lat) / g.res)));
    for (let c = 0; c < g.width; c++) {
      const v = g.values[row * g.width + c];
      const o = (r * g.width + c) * 4;
      if (v === null || v === undefined || Number.isNaN(v)) {
        img.data[o + 3] = 0;
        continue;
      }
      const t = (v - domain[0]) / (domain[1] - domain[0] || 1);
      const [R, G, B, A] = colour(Math.min(1, Math.max(0, t)), RAMPS[ramp]);
      img.data[o] = R;
      img.data[o + 1] = G;
      img.data[o + 2] = B;
      img.data[o + 3] = A;
    }
  }
  ctx.putImageData(img, 0, 0);
  return {
    url: canvas.toDataURL("image/png"),
    coordinates: [
      [minlon, maxlat],
      [maxlon, maxlat],
      [maxlon, minlat],
      [minlon, minlat],
    ] as [[number, number], [number, number], [number, number], [number, number]],
  };
}

export function rampCss(ramp: keyof typeof RAMPS) {
  return `linear-gradient(90deg, ${RAMPS[ramp]
    .map(([t, [r, g, b, a]]) => `rgba(${r},${g},${b},${Math.max(a, 40) / 255}) ${t * 100}%`)
    .join(",")})`;
}
