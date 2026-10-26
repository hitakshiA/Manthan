/**
 * ClerkIdentitySync - bridges Clerk's signed-in user into the api
 * module's per-request identity header.
 *
 * Why: the dev tenant resolver in manthan-api can read an
 * `X-Manthan-Dev-Email` header (or `dev_email` query param for SSE) to
 * map the request to the actual signed-in member instead of "oldest
 * admin in org". Without this bridge, every API call resolves to the
 * seeded `you@miny-labs.com` regardless of who signed in.
 *
 * Mount once near the root, inside ClerkProvider. Renders nothing.
 *
 * On sign-out, clears the cached email so the next session's API
 * calls don't carry a stale identity.
 */

import { useEffect } from "react";
import { useUser } from "@clerk/react";

import { setApiUserEmail } from "@/lib/api";

export function ClerkIdentitySync(): null {
  const { isLoaded, isSignedIn, user } = useUser();

  useEffect(() => {
    if (!isLoaded) return;
    if (isSignedIn && user) {
      const email = user.primaryEmailAddress?.emailAddress ?? null;
      setApiUserEmail(email);
    } else {
      setApiUserEmail(null);
    }
  }, [isLoaded, isSignedIn, user]);

  return null;
}
