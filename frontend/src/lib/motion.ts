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

/** Drawer slide variants (right-side panels) */
export const DRAWER_RIGHT_VARIANTS = {
  hidden: { x: "100%", opacity: 0 },
  visible: {
    x: 0,
    opacity: 1,
    transition: { type: "spring" as const, stiffness: 350, damping: 32 },
  },
  exit: {
    x: "100%",
    opacity: 0,
    transition: { duration: 0.2, ease: EASE_QUANT_OUT },
  },
};

/** Drawer slide variants (bottom sheet for mobile) */
export const DRAWER_BOTTOM_VARIANTS = {
  hidden: { y: "100%", opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: { type: "spring" as const, stiffness: 350, damping: 32 },
  },
  exit: {
    y: "100%",
    opacity: 0,
    transition: { duration: 0.22, ease: EASE_QUANT_OUT },
  },
};

/** Modal backdrop */
export const BACKDROP_VARIANTS = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.15 } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

/** Scale in from center (modals, tooltips) */
export const SCALE_IN_VARIANTS = {
  hidden: { opacity: 0, scale: 0.95, y: -6 },
  visible: {
    opacity: 1,
    scale: 1,
    y: 0,
    transition: { type: "spring" as const, stiffness: 450, damping: 32 },
  },
  exit: {
    opacity: 0,
    scale: 0.97,
    y: -4,
    transition: { duration: 0.15 },
  },
};

/** Fast stagger for large lists */
export const STAGGER_FAST = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.025,
      delayChildren: 0.01,
    },
  },
};

/** Stagger item — left slide (news cards, list items) */
export const STAGGER_ITEM_LEFT = {
  hidden: { opacity: 0, x: -12 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.2, ease: EASE_QUANT_OUT },
  },
};

/** Stagger item — scale pop (badges, pills) */
export const STAGGER_ITEM_SCALE = {
  hidden: { opacity: 0, scale: 0.85 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { type: "spring" as const, stiffness: 350, damping: 25 },
  },
};

/** Tab content switch */
export const TAB_CONTENT_VARIANTS = {
  hidden: (dir: number) => ({ opacity: 0, x: dir > 0 ? 12 : -12 }),
  visible: { opacity: 1, x: 0, transition: { duration: 0.2, ease: EASE_QUANT_OUT } },
  exit: (dir: number) => ({ opacity: 0, x: dir > 0 ? -12 : 12, transition: { duration: 0.15 } }),
};

/** Page transition */
export const PAGE_VARIANTS = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, ease: EASE_QUANT_OUT },
  },
  exit: {
    opacity: 0,
    y: -8,
    transition: { duration: 0.2 },
  },
};

/** Rebalance proposal reveal */
export const REVEAL_HEIGHT_VARIANTS = {
  hidden: { opacity: 0, height: 0, overflow: "hidden" as const },
  visible: {
    opacity: 1,
    height: "auto",
    transition: {
      height: { type: "spring" as const, stiffness: 300, damping: 30 },
      opacity: { duration: 0.2, delay: 0.1 },
    },
  },
  exit: {
    opacity: 0,
    height: 0,
    transition: { height: { duration: 0.2 }, opacity: { duration: 0.1 } },
  },
};
