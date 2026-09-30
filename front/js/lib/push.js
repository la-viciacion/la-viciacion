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

export const pushSupported = () =>
  typeof navigator !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

async function registration() {
  return navigator.serviceWorker.ready;
}

/** This device's current subscription, or null. */
export async function currentSubscription() {
  return (await registration()).pushManager.getSubscription();
}

/** Ask for permission, subscribe this device and register it on the server. */
export async function enablePush({ publicKey, receiveGroup }) {
  if ((await Notification.requestPermission()) !== 'granted') throw new Error('El permiso de notificaciones está denegado en el navegador');
  const subscription =
    (await currentSubscription()) ||
    (await (await registration()).pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) }));
  await api('/push/subscribe', jsonRequest('POST', subscriptionBody(subscription, receiveGroup, navigator.userAgent)));
}

/** Forget this device on the server and in the browser. */
export async function disablePush() {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await api('/push/unsubscribe', jsonRequest('POST', { endpoint: subscription.endpoint }));
  await subscription.unsubscribe();
}

export async function setReceiveGroup(receiveGroup) {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await api('/push/subscription', jsonRequest('PATCH', { endpoint: subscription.endpoint, receive_group: receiveGroup }));
}
