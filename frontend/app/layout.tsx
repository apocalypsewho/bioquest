import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import "./globals.css";
import Shell from "@/components/Shell";
import SWRegister from "@/components/SWRegister";
import { AppProvider } from "@/lib/store";

export const metadata: Metadata = {
  title: "BIOQUEST — Discover what hasn't been mapped yet",
  description: "Biodiversity exploration: occurrences, distribution models, sampling gaps and field missions.",
  manifest: "/manifest.webmanifest",
  applicationName: "BIOQUEST",
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
  appleWebApp: { capable: true, title: "BIOQUEST", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: "#040706",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="font-sans">
        <AppProvider>
          <SWRegister />
          <Shell>{children}</Shell>
        </AppProvider>
      </body>
    </html>
  );
}
