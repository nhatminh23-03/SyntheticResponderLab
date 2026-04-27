import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@/app/globals.css";
import {
  assertProductionAuthConfigured,
  getAppAccessPassword,
  getDeploymentSharedSecret,
  getServerApiBaseUrl,
  isClerkConfigured,
} from "@/lib/server-env";
import { ClerkProvider } from "@clerk/nextjs";

export const metadata: Metadata = {
  title: "Grounded Synthetic Respondent Lab",
  description:
    "Build grounded synthetic personas, run AI-powered survey simulations, and verify realism with trust signals.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  getServerApiBaseUrl();
  getDeploymentSharedSecret();
  getAppAccessPassword();
  assertProductionAuthConfigured();

  const content = (
    <html lang="en">
      <body>{children}</body>
    </html>
  );

  if (isClerkConfigured()) {
    return <ClerkProvider>{content}</ClerkProvider>;
  }

  return content;
}
