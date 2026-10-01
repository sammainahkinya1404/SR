import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "Duka Manager", template: "%s · Duka Manager" },
  description: "Stock, sales, credit, expenses and profit for Kenyan retail shops.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // Browser extensions add attributes to <html> before React loads (e.g. data-qb-installed);
    // ignore those here. This covers only this element's own attributes, not its children.
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
