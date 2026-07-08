import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Tiro_Devanagari_Hindi } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

const tiro = Tiro_Devanagari_Hindi({
  subsets: ["devanagari"],
  weight: "400",
  variable: "--font-devanagari",
});

export const metadata: Metadata = {
  title: "Bahi — bol ke likho",
  description:
    "Voice-first kirana shop manager. Speak in your language; the bahi writes itself.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${plexMono.variable} ${tiro.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
