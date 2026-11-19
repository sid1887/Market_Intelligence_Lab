"use client";

import { useEffect, useRef } from "react";

/**
 * Intercepts Android hardware back button and mobile left-swipe back gestures (via HTML5 History popstate).
 * Pushes a history state when a modal or drawer opens, and closes it smoothly when popstate fires
 * rather than exiting the PWA or browser tab.
 */
export function useBackButtonClose(
  isOpen: boolean,
  onClose: () => void,
  key: string
) {
  const isPushedRef = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (typeof window === "undefined") return;

    if (isOpen) {
      if (!isPushedRef.current) {
        window.history.pushState({ milDrawer: key }, "");
        isPushedRef.current = true;
      }

      const handlePopState = () => {
        isPushedRef.current = false;
        onCloseRef.current();
      };

      window.addEventListener("popstate", handlePopState);

      return () => {
        window.removeEventListener("popstate", handlePopState);
      };
    } else {
      if (isPushedRef.current) {
        isPushedRef.current = false;
        if (window.history.state?.milDrawer === key) {
          window.history.back();
        }
      }
    }
  }, [isOpen, key]);
}
