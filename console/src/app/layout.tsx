import "@/styles/globals.css";

export const metadata = {
  title: "Novak Console",
  description: "Profiles, memory, and the MCP catalog",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
