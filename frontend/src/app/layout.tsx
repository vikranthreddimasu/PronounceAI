import type { Metadata, Viewport } from "next";
import { Inter, Fraunces, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import NavBar from "@/components/NavBar";
import ThemeBoot from "@/components/ThemeBoot";

const sans = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const display = Fraunces({
  variable: "--font-display",
  subsets: ["latin"],
  axes: ["SOFT", "opsz"],
  display: "swap",
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "PronounceAI — speak any accent, with clarity",
  description:
    "Phoneme-level pronunciation feedback. Hear yourself in any accent. Practice with intention.",
};

export const viewport: Viewport = {
  themeColor: "#f5f2ec",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${display.variable} ${mono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="relative min-h-dvh">
        <ThemeBoot />
        <NavBar />
        <div className="relative" style={{ zIndex: 1 }}>
          {children}
        </div>
      </body>
    </html>
  );
}
