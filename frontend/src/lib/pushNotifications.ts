"use client";

import { apiFetch } from "./api";

/**
 * Converts a base64url encoded VAPID public key string into a Uint8Array
 * required by the browser's PushManager API.
 */
export function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export type PushPermissionStatus =
  | "unsupported"
  | "default"
  | "granted"
  | "denied";

export function isPushNotificationSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export async function checkPushSubscription(): Promise<{
  supported: boolean;
  permission: PushPermissionStatus;
  isSubscribed: boolean;
  subscription: PushSubscription | null;
}> {
  if (!isPushNotificationSupported()) {
    return {
      supported: false,
      permission: "unsupported",
      isSubscribed: false,
      subscription: null,
    };
  }

  const permission = Notification.permission as PushPermissionStatus;

  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    return {
      supported: true,
      permission,
      isSubscribed: subscription !== null,
      subscription,
    };
  } catch (err) {
    console.warn("Error inspecting push subscription:", err);
    return {
      supported: true,
      permission,
      isSubscribed: false,
      subscription: null,
    };
  }
}

export async function subscribeToWebPush(): Promise<{
  success: boolean;
  error?: string;
  subscription?: PushSubscription;
}> {
  if (!isPushNotificationSupported()) {
    return {
      success: false,
      error: "Web Push Notifications are not supported in this browser environment.",
    };
  }

  try {
    // 1. Request notification permission
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      return {
        success: false,
        error: "Notification permission was denied or dismissed.",
      };
    }

    // 2. Register zero-cache pass-through service worker
    const registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
    });
    await navigator.serviceWorker.ready;

    // 3. Fetch backend VAPID public key
    const vapidRes = await apiFetch<{ public_key: string }>("/push/vapid-public-key");
    if (!vapidRes?.public_key) {
      throw new Error("Invalid VAPID public key received from backend API.");
    }

    const applicationServerKey = urlBase64ToUint8Array(vapidRes.public_key);

    // Unsubscribe existing stale subscription if any to ensure fresh alignment with backend VAPID key
    try {
      const existingSub = await registration.pushManager.getSubscription();
      if (existingSub) {
        await existingSub.unsubscribe();
      }
    } catch {
      // Continue even if unsubscribe fails
    }

    // 4. Subscribe with PushManager
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: applicationServerKey as unknown as BufferSource,
    });

    // 5. Serialize subscription keys to base64
    const rawKey = subscription.getKey("p256dh");
    const rawAuth = subscription.getKey("auth");
    if (!rawKey || !rawAuth) {
      throw new Error("Unable to extract subscription crypto keys.");
    }

    const p256dh = btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(rawKey))));
    const auth = btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(rawAuth))));

    // 6. Post subscription to backend SQLite store
    await apiFetch("/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        keys: { p256dh, auth },
        user_agent: navigator.userAgent,
      }),
    });

    return { success: true, subscription };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("Web Push subscription failed:", err);
    return { success: false, error: msg };
  }
}

/**
 * Silently synchronizes the device's push subscription with the backend if
 * permission is already granted in the browser. Ensures Render's SQLite store
 * has this device registered even after cold restarts without prompting the user.
 */
export async function autoSyncPushSubscription(): Promise<{
  isSubscribed: boolean;
  permission: PushPermissionStatus;
}> {
  if (!isPushNotificationSupported()) {
    return { isSubscribed: false, permission: "unsupported" };
  }

  const permission = Notification.permission as PushPermissionStatus;
  if (permission !== "granted") {
    return { isSubscribed: false, permission };
  }

  try {
    const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;

    let subscription = await registration.pushManager.getSubscription();

    const vapidRes = await apiFetch<{ public_key: string }>("/push/vapid-public-key");
    if (!vapidRes?.public_key) {
      return { isSubscribed: subscription !== null, permission };
    }

    if (!subscription) {
      const applicationServerKey = urlBase64ToUint8Array(vapidRes.public_key);
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey as unknown as BufferSource,
      });
    }

    if (subscription) {
      const rawKey = subscription.getKey("p256dh");
      const rawAuth = subscription.getKey("auth");
      if (rawKey && rawAuth) {
        const p256dh = btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(rawKey))));
        const auth = btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(rawAuth))));

        await apiFetch("/push/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            endpoint: subscription.endpoint,
            keys: { p256dh, auth },
            user_agent: navigator.userAgent,
          }),
        });
        return { isSubscribed: true, permission };
      }
    }
  } catch (err) {
    console.warn("Background push auto-sync failed:", err);
  }

  return { isSubscribed: false, permission };
}

export async function sendTestPushAlert(): Promise<{
  success: boolean;
  message?: string;
  total?: number;
  sent?: number;
}> {
  try {
    const res = await apiFetch<{
      status: string;
      message?: string;
      result?: { sent?: number; total?: number; failed?: number; errors?: string[] };
    }>("/push/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "MIL Quant · Push Verified",
        body: "Real-time causal catalyst notifications active. Institutional market radar connected.",
        url: "/",
      }),
    });

    const total = res.result?.total ?? 0;
    const sent = res.result?.sent ?? 0;

    if (res.status === "warning" || total === 0) {
      return {
        success: false,
        total,
        sent,
        message:
          res.message ||
          "No active push subscriptions registered on server. Tap 'Enable Mobile Push Notifications' to register this device.",
      };
    }

    if (res.status === "error" || sent === 0) {
      const errDetail = res.result?.errors?.join("; ") || res.message || "Failed to deliver push notification.";
      return {
        success: false,
        total,
        sent,
        message: errDetail,
      };
    }

    return {
      success: true,
      total,
      sent,
      message: res.message || `Delivered test alert to ${sent} of ${total} device(s).`,
    };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return { success: false, message: `Failed to trigger test push: ${msg}` };
  }
}
