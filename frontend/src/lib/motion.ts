/**
 * Shared Framer Motion transitions, spring dynamics, and stagger variants
 * for Market Intelligence Lab terminal interfaces.
 */

export const SPRING_SNAPPY = {
  type: "spring" as const,
  stiffness: 400,
  damping: 30,
};

export const SPRING_SMOOTH = {
  type: "spring" as const,
  stiffness: 300,
  damping: 28,
};

export const SPRING_GENTLE = {
  type: "spring" as const,
  stiffness: 240,
  damping: 24,
};

export const EASE_QUANT_OUT = [0.16, 1, 0.3, 1] as const;

export const FADE_IN_VARIANTS = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.25, ease: EASE_QUANT_OUT } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

export const STAGGER_CONTAINER = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.06,
      delayChildren: 0.02,
    },
  },
};

export const STAGGER_ITEM_UP = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.22, ease: EASE_QUANT_OUT },
  },
};

export const STAGGER_ITEM_RIGHT = {
  hidden: { opacity: 0, x: -8 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.22, ease: EASE_QUANT_OUT },
  },
};
