// Web Push subscription of this device (the PWA's notifications).
// The server side is /api/v1/push/*; the worker that shows them is sw.js.
import { api, jsonRequest } from './api.js';

/** Base64url public key (as the server gives it) to the bytes pushManager.subscribe expects. */
export function urlBase64ToUint8Array(base64) {
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

/** Body of POST /push/subscribe for a PushSubscription (its toJSON()). */
export function subscriptionBody(subscription, receiveGroup, userAgent = '') {
  const { endpoint, keys } = subscription.toJSON();
  return { endpoint, keys: { p256dh: keys.p256dh, auth: keys.auth }, receive_group: receiveGroup, user_agent: userAgent.slice(0, 255) || null };
}

/** "Chrome · Android" from a user agent string (best effort, only to tell devices apart). */
export function deviceLabel(userAgent) {
  const ua = userAgent || '';
  const system = /iPhone|iPad|iPod/.test(ua) ? 'iOS' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac OS X|Macintosh/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : '';
  const browser = /Edg\//.test(ua) ? 'Edge' : /OPR\/|Opera/.test(ua) ? 'Opera' : /Firefox|FxiOS/.test(ua) ? 'Firefox' : /Chrome|CriOS/.test(ua) ? 'Chrome' : /Safari/.test(ua) ? 'Safari' : '';
  return [browser, system].filter(Boolean).join(' · ') || 'Dispositivo';
}

/** iPhone/iPad only deliver push to an app added to the home screen. */
export function needsInstall(userAgent, standalone) {
  return /iPhone|iPad|iPod/.test(userAgent || '') && !standalone;
}

export const pushSupported = () =>
  typeof navigator !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

// `ready` never settles if the worker failed to register: do not hang the page on it
async function registration() {
  const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error('El navegador no ha podido activar el servicio de notificaciones')), 4000));
  return Promise.race([navigator.serviceWorker.ready, timeout]);
}

/** This device's current subscription, or null (also when notifications cannot work here). */
export async function currentSubscription() {
  try {
    return await (await registration()).pushManager.getSubscription();
  } catch {
    return null;
  }
}

/** Ask for permission, subscribe this device and register it on the server. */
export async function enablePush({ publicKey, receiveGroup }) {
  if ((await Notification.requestPermission()) !== 'granted') throw new Error('El permiso de notificaciones está denegado en el navegador');
  const subscription =
    (await currentSubscription()) ||
    (await (await registration()).pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) }));
  await api('/push/subscribe', jsonRequest('POST', subscriptionBody(subscription, receiveGroup, navigator.userAgent)));
}

/** Forget a device of the user on the server (and in the browser if it is this one). */
export async function removeDevice(endpoint) {
  await api('/push/unsubscribe', jsonRequest('POST', { endpoint }));
  const subscription = pushSupported() ? await currentSubscription() : null;
  if (subscription && subscription.endpoint === endpoint) await subscription.unsubscribe();
}

export async function setReceiveGroup(endpoint, receiveGroup) {
  await api('/push/subscription', jsonRequest('PATCH', { endpoint, receive_group: receiveGroup }));
}
