import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        obsidian: "#050811",
        "surface-1": "rgba(15, 23, 42, 0.6)",
        "surface-2": "rgba(2, 6, 23, 0.7)",
      },
      keyframes: {
        'tick-up': { '0%': { backgroundColor: 'rgba(16, 185, 129, 0.35)', color: '#34d399' }, '100%': { backgroundColor: 'transparent' } },
        'tick-down': { '0%': { backgroundColor: 'rgba(244, 63, 94, 0.35)', color: '#fb7185' }, '100%': { backgroundColor: 'transparent' } },
        'radar-pulse': { '0%': { transform: 'scale(0.95)', opacity: '0.8' }, '50%': { transform: 'scale(1.4)', opacity: '0' }, '100%': { transform: 'scale(0.95)', opacity: '0' } },
      },
      animation: {
        'tick-up': 'tick-up 450ms cubic-bezier(0.16, 1, 0.3, 1)',
        'tick-down': 'tick-down 450ms cubic-bezier(0.16, 1, 0.3, 1)',
        'radar': 'radar-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
};
export default config;
