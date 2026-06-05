import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { defaultLocale, type Locale, locales } from "./config";

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const localeCookie = cookieStore.get("NEXT_LOCALE")?.value;
  const locale: Locale =
    localeCookie && locales.includes(localeCookie as Locale) ? (localeCookie as Locale) : defaultLocale;

  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
