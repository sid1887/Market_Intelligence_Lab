import { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Market Intelligence Lab",
    short_name: "MIL Quant",
    description: "Institutional-Grade Quantitative Intelligence & Real-Time Causal Catalyst Radar",
    start_url: "/",
    display: "standalone",
    background_color: "#040609",
    theme_color: "#040609",
    orientation: "portrait-primary",
    icons: [
      {
        src: "/icons/icon-192x192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/icons/icon-512x512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
