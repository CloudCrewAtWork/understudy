/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#0A0B0D",
          raised: "#131418",
          pressed: "#1B1D22",
        },
        border: {
          subtle: "#1F2127",
          DEFAULT: "#2A2D34",
          emph: "#3A3E47",
        },
        fg: {
          primary: "#ECEDEE",
          secondary: "#9BA0A8",
          tertiary: "#5C616B",
          disabled: "#383B42",
        },
        accent: {
          DEFAULT: "#FF5C1A",
          hover: "#FF6E33",
          pressed: "#E84F12",
        },
        ok: "#4ADE80",
        warn: "#FBBF24",
        danger: "#F43F5E",
        edit: {
          live: "#B8FF3C",
        },
      },
      fontFamily: {
        sans: ["Geist", "ui-sans-serif", "system-ui"],
        mono: ["Geist Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        caption: ["11px", { lineHeight: "14px" }],
        label: ["12px", { lineHeight: "16px", letterSpacing: "0" }],
        body: ["14px", { lineHeight: "20px", letterSpacing: "-0.01em" }],
        head: ["13px", { lineHeight: "16px", letterSpacing: "0.06em" }],
        title: ["20px", { lineHeight: "24px", letterSpacing: "-0.02em" }],
      },
      borderRadius: {
        xs: "4px",
        sm: "6px",
        md: "8px",
        lg: "10px",
      },
      keyframes: {
        "sweep-x": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        "flash-live": {
          "0%": { backgroundColor: "rgba(184, 255, 60, 0.14)" },
          "100%": { backgroundColor: "rgba(184, 255, 60, 0)" },
        },
      },
      animation: {
        "sweep-x": "sweep-x 1.2s linear infinite",
        "flash-live": "flash-live 1.2s ease-out",
      },
    },
  },
  plugins: [],
};
