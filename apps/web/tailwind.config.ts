import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17211b",
        paper: "#f6f4ef",
        line: "#e4ddd2",
        pine: "#1f6b4a",
      },
    },
  },
  plugins: [],
};

export default config;
