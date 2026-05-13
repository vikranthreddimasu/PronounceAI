import type { Metadata, Viewport } from "next";
import "./globals.css";
import NavBar from "@/components/NavBar";
import ThemeBoot from "@/components/ThemeBoot";

export const metadata: Metadata = {
  title: "PronounceAI - phoneme-level accent coaching",
  description:
    "A calm NLP pronunciation coach with phoneme-level scoring, prosody overlays, and accent-aware audio feedback.",
};

export const viewport: Viewport = {
  themeColor: "#f5f2e8",
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
      className="h-full antialiased"
      suppressHydrationWarning
    >
      <body className="relative min-h-dvh">
        <ThemeBoot />
        <NavBar />
        <div className="app-content relative" style={{ zIndex: 1 }}>
          {children}
        </div>
      </body>
    </html>
  );
}
