"use client";

import { SignedIn, UserButton } from "@clerk/nextjs";

export function UserMenuSlot() {
  const isClerkConfigured =
    (process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.trim() || "") !== "";

  if (!isClerkConfigured) {
    return null;
  }

  return (
    <SignedIn>
      <div className="flex items-center">
        <UserButton
          afterSignOutUrl="/"
          appearance={{
            elements: {
              userButtonAvatarBox:
                "h-9 w-9 ring-1 ring-app-cyan/25 hover:ring-app-cyan/50 transition",
            },
          }}
        />
      </div>
    </SignedIn>
  );
}
