import type { Metadata, Viewport } from "next";
import { Sofia_Sans, Sofia_Sans_Extra_Condensed } from "next/font/google";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { site } from "@/lib/site";
import "./globals.css";

const sofia = Sofia_Sans({ subsets: ["latin"], variable: "--font-sofia", display: "swap" });
const sofiaXC = Sofia_Sans_Extra_Condensed({ subsets: ["latin"], variable: "--font-sofia-xc", display: "swap" });

export const metadata: Metadata = {
  title: { default: `${site.name}: ${site.tagline}`, template: `%s | ${site.name}` },
  description:
    "A five-servo desktop robot arm, designed in SolidWorks and 3D printed by three University of Waterloo students. Try its inverse kinematics in your browser, and read how it was designed, wired and programmed.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f5c4b",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sofia.variable} ${sofiaXC.variable}`}>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <SiteHeader />
        <main id="main">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
