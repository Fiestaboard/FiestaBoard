# Localization (i18n)

FiestaBoard supports multiple languages through community-maintained translations.

## Supported Languages

| Language            | Code | Status |
|---------------------|------|--------|
| English             | `en` | ✅ Default |
| Spanish             | `es` | ✅ Available |
| French              | `fr` | ✅ Available |
| German              | `de` | ✅ Available |
| Italian             | `it` | ✅ Available |
| Portuguese          | `pt` | ✅ Available |
| Dutch               | `nl` | ✅ Available |
| Polish              | `pl` | ✅ Available |
| Russian             | `ru` | ✅ Available |
| Swedish             | `sv` | ✅ Available |
| Turkish             | `tr` | ✅ Available |
| Japanese            | `ja` | ✅ Available |
| Korean              | `ko` | ✅ Available |
| Chinese (Simplified)| `zh` | ✅ Available |

## Changing Language

Use the language selector in the sidebar footer to switch between available languages. Your preference is saved and persists across sessions.

## About Translations

:::info Community Maintained
Translations in FiestaBoard were initially generated with the help of an LLM (Large Language Model) and are community maintained. While LLM-generated translations provide a solid starting point, they may not always capture the perfect phrasing or local idioms for every language.

We welcome and encourage contributions from native speakers to improve translation quality.
:::

## Contributing Translations

Translation files are located in `web/messages/` as JSON files (one per language). To improve an existing translation or add a new language:

1. **Improve existing translations**: Edit the appropriate file in `web/messages/` (e.g., `es.json` for Spanish)
2. **Add a new language**: 
   - Copy `web/messages/en.json` to `web/messages/{locale}.json`
   - Translate all values (keep the JSON keys unchanged)
   - Add the locale to `web/src/i18n/config.ts`
3. **Submit a pull request** with your changes

### Translation File Structure

Each translation file is a JSON object organized by feature namespace:

```json
{
  "common": {
    "save": "Save",
    "cancel": "Cancel"
  },
  "navigation": {
    "home": "Home",
    "pages": "Pages"
  }
}
```

### Guidelines

- Keep `{variable}` interpolation placeholders exactly as they are
- Use ICU message format for plurals: `{count, plural, one {# page} other {# pages}}`
- Don't translate the brand names "FiestaBoard" or "Vestaboard"
- Technical terms (API, URL, JSON) should generally stay in English
- Test your translations by switching to the language in the UI

### Lint Rule

An ESLint rule (`i18next/no-literal-string`) is configured to warn when hardcoded strings are found in JSX that should be using translations. Run `npm run lint` in the `web/` directory to check for missed translations.
