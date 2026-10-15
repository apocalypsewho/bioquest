"use client";
/**
 * Offline field queue (IndexedDB). Observations + their media are stored locally when the network
 * (or the API) is unavailable and uploaded later. Each item has a client_uuid so re-sending is idempotent.
 */
import { api, getToken, API_URL } from "./api";

const DB = "bioquest-offline";
const STORE = "queue";

type Item = { client_uuid: string; observation: Record<string, unknown>; media: { name: string; type: string; blob: Blob }[] };

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "client_uuid" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const r = fn(t.objectStore(STORE));
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

export async function enqueue(item: Item) {
  await tx("readwrite", (s) => s.put(item));
}

export async function queueSize(): Promise<number> {
  try {
    return await tx("readonly", (s) => s.count());
  } catch {
    return 0;
  }
}

export async function listQueue(): Promise<Item[]> {
  try {
    return await tx("readonly", (s) => s.getAll() as IDBRequest<Item[]>);
  } catch {
    return [];
  }
}

export async function uploadMedia(obsId: number, media: Item["media"]) {
  for (const m of media) {
    const fd = new FormData();
    fd.append("file", new File([m.blob], m.name, { type: m.type }));
    const res = await fetch(`${API_URL}/api/observations/${obsId}/photos`, {
      method: "POST",
      body: fd,
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) throw new Error(`media upload failed (${res.status})`);
  }
}

export async function flushQueue(): Promise<number> {
  if (!getToken()) return 0;
  const items = await listQueue();
  let done = 0;
  for (const it of items) {
    try {
      const r = await api<{ synced: { client_uuid: string; id: number; created: boolean }[] }>("/api/observations/sync", {
        method: "POST",
        json: { observations: [{ ...it.observation, client_uuid: it.client_uuid }] },
      });
      const s = r.synced[0];
      if (s.created) await uploadMedia(s.id, it.media);
      await tx("readwrite", (st) => st.delete(it.client_uuid));
      done++;
    } catch {
      break; // still offline / API down: keep the rest queued
    }
  }
  return done;
}

export function uuid() {
  return (crypto as Crypto & { randomUUID?: () => string }).randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
