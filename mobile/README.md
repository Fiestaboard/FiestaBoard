# FiestaBoard Mobile App

React Native iOS companion app for FiestaBoard, built with Expo.

## Prerequisites

- Node.js 20+
- [pnpm](https://pnpm.io/) 9+
- Xcode 16+ (for iOS simulator/device)
- [Expo CLI](https://docs.expo.dev/get-started/installation/)

## Getting Started

```bash
# From the monorepo root
pnpm install

# Start the Expo dev server
pnpm dev:mobile

# Or from the mobile directory
cd mobile
pnpm start
```

## Connecting to Your Server

On first launch, the app will ask for your FiestaBoard server URL. Enter the URL where your FiestaBoard instance is running (e.g., `http://fiestaboard.local:4420` or `http://192.168.1.100:4420`).

Make sure your phone and FiestaBoard server are on the same local network.

## Architecture

The mobile app shares platform-agnostic code with the web UI via the `@fiestaboard/shared` package:

```
packages/shared/     → API types, client, board colors, utilities
mobile/
├── app/             → Expo Router screens (file-based routing)
├── components/      → React Native UI components
├── hooks/           → TanStack Query hooks
└── lib/             → API client, storage, theme
```

### Screens

| Screen | Description |
|--------|-------------|
| Dashboard | Board preview, service status, active page |
| Pages | Page list with previews, create/edit pages |
| Schedule | Calendar view + list of schedule entries |
| Integrations | Plugin list with enable/disable and config |
| Settings | Server connection, general config, boards |

### Key Dependencies

- **Expo SDK 52** — React Native framework
- **Expo Router** — File-based navigation with native tab bar
- **@tanstack/react-query** — Server state management (shared with web)
- **@fiestaboard/shared** — Shared API types, client, and utilities
- **react-native-big-calendar** — Weekly schedule calendar view
- **lucide-react-native** — Icons (same set as web)

## Development Notes

- The app connects to the same REST API that the web UI uses
- Server URL is stored securely via `expo-secure-store`
- Pull-to-refresh is available on all data screens
- Dark mode follows iOS system appearance automatically
- The page editor uses a TextInput-based approach (upgradeable to TenTap/TipTap for development builds)

## Building for Device

```bash
# Generate native iOS project
npx expo prebuild

# Build for iOS simulator
npx expo run:ios

# Build for device (requires Apple Developer account)
npx expo run:ios --device
```
