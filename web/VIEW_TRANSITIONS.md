# Page Transitions Implementation

This document describes the page transitions implementation in the FiestaBoard web UI.

## Overview

We use CSS-based page transitions to create smooth, polished page-to-page navigation with:
- **Mixed transition styles**: Fade-slide, slide-up, slide-down, and scale animations
- **Fast animations**: 300-350ms durations for snappy, responsive feel
- **Universal browser support**: Works in all modern browsers including Safari
- **Full accessibility**: Respects `prefers-reduced-motion` preference

## Why CSS Transitions Instead of View Transitions API?

While the View Transitions API is powerful, it has limitations with Next.js App Router:
- **Async navigation**: Next.js router updates are inherently async, causing flickering
- **Browser support**: Limited to Chrome 111+, Safari 18+ (macOS Sonoma 14.4+)
- **Complexity**: Requires synchronous DOM updates that Next.js can't guarantee

CSS transitions provide:
- ✅ **Reliable**: Work consistently across all browsers
- ✅ **Simple**: No complex API coordination needed
- ✅ **Performant**: GPU-accelerated transforms
- ✅ **Accessible**: Built-in `prefers-reduced-motion` support

## Architecture

### Core Components

1. **`ViewTransitionLink`** (`components/view-transition-link.tsx`)
   - Wrapper around Next.js `Link` component
   - Applies transition type via data attribute on `<html>`
   - Cleans up after navigation completes
   - Supports transition type prop for context-specific animations

2. **`useViewTransition`** (`hooks/use-view-transition.ts`)
   - Hook for programmatic navigation with transitions
   - Provides `push()`, `replace()`, and `back()` methods
   - Applies CSS transition classes
   - Used for save/cancel buttons and programmatic navigation

3. **`ViewTransitionLoading`** (`components/view-transition-loading.tsx`)
   - Subtle loading indicator for slow page loads
   - Shows progress bar at top of screen
   - Provides visual feedback during navigation

### Transition Types

| Type | Duration | Animation | Use Case |
|------|----------|-----------|----------|
| `default` | 300ms | Fade + slight upward movement | Standard page navigation |
| `slide-up` | 350ms | Slide up + scale + fade | Opening modal-like pages (edit/new) |
| `slide-down` | 300ms | Slide down + fade | Closing modal-like pages (back to list) |
| `scale-fade` | 300ms | Scale + fade | Content areas appearing |

### How It Works

1. **User clicks link** → `ViewTransitionLink` sets `data-transition` attribute on `<html>`
2. **Next.js navigates** → Route change triggers
3. **New page loads** → `<main>` element animates in based on `data-transition` value
4. **Animation completes** → `data-transition` attribute is removed

The CSS animations are applied to the `<main>` element, creating smooth transitions for all page content.

## Browser Support

- **All modern browsers**: Chrome, Firefox, Safari, Edge
- **Mobile**: iOS Safari, Chrome Mobile, Samsung Internet
- **Performance**: GPU-accelerated CSS transforms work everywhere
- **No fallback needed**: CSS animations are universally supported

## Accessibility

### Reduced Motion

The implementation fully respects the `prefers-reduced-motion` user preference:

```css
@media (prefers-reduced-motion: reduce) {
  main {
    animation: none !important;
  }
}
```

When a user has reduced motion enabled, all page transition animations are completely disabled.

### Keyboard Navigation

- All `ViewTransitionLink` components maintain full keyboard accessibility
- Tab navigation works naturally
- Enter/Space keys trigger navigation with transitions
- Screen readers announce navigation normally

### Focus Management

- Focus is preserved during transitions
- No focus traps or keyboard navigation issues
- Follows standard Next.js routing behavior

## Usage Examples

### Using ViewTransitionLink

```tsx
import { ViewTransitionLink } from "@/components/view-transition-link";

// Default transition (fade + slide)
<ViewTransitionLink href="/dashboard">
  Go to Dashboard
</ViewTransitionLink>

// Slide-up transition (for modal-like pages)
<ViewTransitionLink 
  href="/pages/new" 
  transitionType="slide-up"
>
  Create New Page
</ViewTransitionLink>
```

### Using useViewTransition Hook

```tsx
import { useViewTransition } from "@/hooks/use-view-transition";

function MyComponent() {
  const { push, back } = useViewTransition();

  const handleSave = () => {
    // Save data...
    push("/pages", { transitionType: "slide-down" });
  };

  const handleCancel = () => {
    back({ transitionType: "slide-down" });
  };

  return (
    <>
      <button onClick={handleSave}>Save</button>
      <button onClick={handleCancel}>Cancel</button>
    </>
  );
}
```

### Custom Transition Types

All transitions are CSS-based. To add a new transition type:

1. Add CSS keyframe animation in `globals.css`:
```css
@keyframes my-custom-enter {
  from {
    opacity: 0;
    transform: rotate(5deg);
  }
  to {
    opacity: 1;
    transform: rotate(0deg);
  }
}
```

2. Add transition rule:
```css
html[data-transition="custom"] main {
  animation: my-custom-enter 400ms ease-out;
}
```

3. Use in your component:
```tsx
<ViewTransitionLink href="/page" transitionType="custom">
  Link
</ViewTransitionLink>
```

## Testing

### Manual Testing Checklist

- [ ] Navigate between all pages (Dashboard, Pages, Settings, Logs)
- [ ] Click page cards to enter edit mode (slide-up)
- [ ] Return from edit mode (slide-down)
- [ ] Verify page headers morph between pages
- [ ] Check navigation indicator animates
- [ ] Test with keyboard only (Tab, Enter, Space)
- [ ] Enable "Reduce Motion" in OS settings and verify instant transitions
- [ ] Test in Chrome, Safari, and Firefox
- [ ] Verify fallback works in older browsers

### Browser DevTools Testing

1. Open Chrome DevTools
2. Go to "Animations" panel (Cmd+Shift+P → "Show Animations")
3. Navigate between pages
4. Observe view transition animations
5. Verify timing (200-300ms)

### Reduced Motion Testing

**macOS:**
- System Settings → Accessibility → Display → Reduce Motion

**Windows:**
- Settings → Accessibility → Visual Effects → Animation Effects (Off)

**Chrome DevTools:**
- Cmd+Shift+P → "Emulate CSS prefers-reduced-motion"

## Performance Considerations

- **GPU-accelerated**: Uses `transform` and `opacity` for 60fps animations
- **Lightweight**: Pure CSS, no JavaScript during animation
- **No layout shift**: Animations don't affect document flow
- **Fast**: 300-350ms durations feel snappy and responsive
- **Reduced motion**: Completely disabled when user prefers reduced motion
- **No bundle size impact**: CSS-only solution

## Future Enhancements

Potential improvements for the future:

1. **Stagger animations**: Animate list items sequentially
2. **Directional transitions**: Detect forward/back navigation for appropriate animations
3. **Skeleton screens**: Show content structure during slow data loads
4. **Gesture support**: Swipe gestures on mobile devices
5. **Page-specific transitions**: Custom animations for specific routes
6. **View Transitions API**: When Next.js App Router properly supports it

## Troubleshooting

### Transitions not appearing

1. **Check CSS is loaded**: Open DevTools → Elements → Check `<main>` element has animations
2. **Verify timing**: Animations are 300-350ms, very fast - might be easy to miss
3. **Test reduced motion**: Disable "Reduce Motion" in your OS accessibility settings
4. **Check browser console**: Look for any CSS errors

### Transitions feel janky

1. **GPU acceleration**: Ensure using `transform` and `opacity` only (already done)
2. **Reduce complexity**: Remove heavy JavaScript during page transitions
3. **Check performance**: Open DevTools → Performance tab, record a navigation
4. **Browser extensions**: Disable extensions that might interfere with animations

### Transitions don't work in specific browser

1. **Clear cache**: Hard refresh (Cmd/Ctrl + Shift + R)
2. **Check CSS support**: All modern browsers support CSS animations
3. **Test in incognito**: Rule out extension interference
4. **Update browser**: Ensure you're on a recent version

### Keyboard navigation issues

1. Verify all interactive elements have proper focus styles
2. Check tab order is logical
3. Test with screen reader (VoiceOver/NVDA)
4. Ensure no focus traps
5. Test Enter/Space keys trigger navigation properly

## Resources

- [MDN: CSS Animations](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Animations/Using_CSS_animations)
- [MDN: CSS Transforms](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Transforms/Using_CSS_transforms)
- [CSS Tricks: Performant Animations](https://css-tricks.com/animating-layouts-with-the-flip-technique/)
- [WCAG: Animation from Interactions](https://www.w3.org/WAI/WCAG21/Understanding/animation-from-interactions.html)
- [Web.dev: Animations Performance](https://web.dev/animations/)

