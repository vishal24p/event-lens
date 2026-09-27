import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Event Lens — listening booth",
  description: "Booth console for capturing spoken visitor feedback.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#booth-main">
          Skip to booth controls
        </a>
        {children}
      </body>
    </html>
  );
}
