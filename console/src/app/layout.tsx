import "@/styles/globals.css";

export const metadata = {
  title: "Novak Console",
  description: "What Novak did today, what it remembers, and what is waiting for your yes",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
