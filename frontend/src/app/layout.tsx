import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "Market Intelligence Lab — Quantitative Terminal",
  description:
    "High-performance quantitative market research and equity attribution terminal. Local-first SQLite, multi-factor quality-momentum, GARCH forecasting.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-[#030508] text-slate-100 antialiased selection:bg-cyan-500/20 selection:text-cyan-300 overflow-hidden">
        {children}
      </body>
    </html>
  );
}
