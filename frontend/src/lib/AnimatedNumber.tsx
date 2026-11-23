"use client";

import React, { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

export interface AnimatedNumberProps {
  value: number;
  duration?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
  formatFn?: (n: number) => string;
}

export function AnimatedNumber({
  value,
  duration = 700,
  decimals = 2,
  prefix = "",
  suffix = "",
  className,
  formatFn,
}: AnimatedNumberProps) {
  const shouldReduceMotion = useReducedMotion();
  const [display, setDisplay] = useState(shouldReduceMotion ? value : 0);

  useEffect(() => {
    if (shouldReduceMotion) {
      setDisplay(value);
      return;
    }

    const startValue = 0;
    const startTime = performance.now();

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = startValue + (value - startValue) * eased;
      setDisplay(current);

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        setDisplay(value);
      }
    };

    const raf = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf);
  }, [value, duration, shouldReduceMotion]);

  const formatted = formatFn
    ? formatFn(display)
    : display.toLocaleString("en-IN", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });

  return (
    <span className={className}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}

export default AnimatedNumber;
