import type { Metadata } from "next";
import "./globals.css";

// App-wide browser metadata used by Next.js for the document head.
export const metadata: Metadata = {
  title: "Polymarket Flow Analyzer",
  description: "Analyze Polymarket trade flow, wallet behavior, and shadow signals.",
};

// RootLayout is required by the Next.js App Router and wraps every page.
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
