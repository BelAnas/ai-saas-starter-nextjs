import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every page behind sign-in depends on the visitor's cookie, so pages are rendered per
  // request. Static prerendering and its cache rules would add complexity for no gain here.
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
