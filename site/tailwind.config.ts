import type { Config } from "tailwindcss";

// Design tokens. Provisional: Vyom owns the final token set and shell (see site/README.md).
const config: Config = {
  // Hover styles only where hover exists: touch fires false hovers on tap.
  future: { hoverOnlyWhenSupported: true },
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B0D10",
        panel: "#10141A",
        raised: "#151A21",
        paper: "#F3F4F6",
        mute: "#8B94A3",
        hair: "rgba(255,255,255,0.08)",
        signal: "#FF6A1A", // safety orange: the active joint
        scope: "#22D3EE", // electric cyan: telemetry
      },
      fontFamily: {
        sans: ["'Space Grotesk Variable'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono Variable'", "ui-monospace", "monospace"],
      },
      transitionTimingFunction: {
        crisp: "cubic-bezier(0.23, 1, 0.32, 1)",
      },
    },
  },
  plugins: [],
};
export default config;
