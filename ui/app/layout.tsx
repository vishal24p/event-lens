import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "feedback-llm",
  description: "Operator console for visitor feedback capture.",
};

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
