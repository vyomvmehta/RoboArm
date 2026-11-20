import type { Metadata } from "next";
import "@fontsource-variable/space-grotesk";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";
import DotGrid from "@/components/DotGrid";
import ScrollHud from "@/components/ScrollHud";
import { Footer, Nav } from "@/components/Shell";
import { loadArm } from "@/lib/repo";

export const metadata: Metadata = {
  title: { default: "RoboArm", template: "%s · RoboArm" },
  description: "A 5-DOF desktop robot arm built by three University of Waterloo Mechatronics students: electronics, firmware, protocol and the build log.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const arm = loadArm();
  return (
    <html lang="en">
      <body>
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-ink focus:px-3 focus:py-2">
          Skip to content
        </a>
        <DotGrid />
        <Nav />
        <main id="main">{children}</main>
        <Footer />
        <ScrollHud limits={arm.joints[1].limits!} />
      </body>
    </html>
  );
}
