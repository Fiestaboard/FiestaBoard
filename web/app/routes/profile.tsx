import { useEffect } from "react";

import { useRouter } from "@/hooks/use-router";

export default function ProfilePage() {
  const router = useRouter();

  useEffect(() => {
    // A profile is your account (Settings › Account). With Account hidden
    // (auth on, signed out) the settings route sends this on to its index.
    router.replace("/settings/account");
  }, [router]);

  return null;
}
