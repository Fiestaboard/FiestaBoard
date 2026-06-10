import { useEffect } from "react";

import { useRouter } from "@/hooks/use-router";

export default function ProfilePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/settings?section=general");
  }, [router]);

  return null;
}
