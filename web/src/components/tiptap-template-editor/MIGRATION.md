# Migration Guide: TipTap Rich Template Editor

This guide explains how to migrate from the old `TemplateLineEditor` to the new `TipTapLineEditor`.

## Quick Start

The new editor is a **drop-in replacement** with the same interface:

```tsx
// Old
import { TemplateLineEditor } from '@/components/template-line-editor';

// New
import { TipTapLineEditor } from '@/components/tiptap-template-editor/TipTapLineEditor';

// Interface is identical
<TipTapLineEditor
  value={templateLine}
  onChange={setTemplateLine}
  placeholder="Type or insert variables..."
  isActive={isActive}
  hasWarning={hasWarning}
/>
```

## Feature Flag Approach

For gradual rollout, use environment variables and localStorage:

### Step 1: Add Environment Variable

Add to `.env.local` or `.env`:

```env
NEXT_PUBLIC_USE_TIPTAP_EDITOR=true
```

### Step 2: Conditional Component

```tsx
import { TemplateLineEditor } from '@/components/template-line-editor';
import { TipTapLineEditor } from '@/components/tiptap-template-editor/TipTapLineEditor';

function PageBuilder() {
  const useTipTap = process.env.NEXT_PUBLIC_USE_TIPTAP_EDITOR === 'true';
  
  const Editor = useTipTap ? TipTapLineEditor : TemplateLineEditor;
  
  return (
    <Editor
      value={line}
      onChange={setLine}
      // ... other props
    />
  );
}
```

### Step 3: Per-User Override (Optional)

Users can override the default in browser console:

```javascript
// Enable TipTap editor
localStorage.setItem('use_tiptap_editor', 'true');
location.reload();

// Disable TipTap editor
localStorage.setItem('use_tiptap_editor', 'false');
location.reload();

// Use environment default
localStorage.removeItem('use_tiptap_editor');
location.reload();
```

## Compatibility

### What's Compatible

✅ All template syntax (variables, colors, symbols, fill_space, alignment)
✅ Template storage format (no database migration)
✅ Backend template engine (no changes needed)
✅ Existing templates (parse and display correctly)
✅ Component interface (same props)

### What's Different

🎨 **Visual appearance**: Rich inline nodes instead of raw syntax
🖱️ **Interaction**: Click to delete, drag to reorder
📊 **Metrics**: Real-time character counts (optional)
⌨️ **Editing**: More visual, less typing of brackets

## Testing Plan

### Phase 1: Development Testing
- [ ] Enable in dev environment
- [ ] Test all template syntax types
- [ ] Verify serialization matches old format
- [ ] Check character counting accuracy
- [ ] Test edge cases (empty, overflow, etc.)

### Phase 2: Beta Testing
- [ ] Enable for admin users only
- [ ] Collect feedback on usability
- [ ] Monitor for bugs or issues
- [ ] Compare templates created with old vs new editor

### Phase 3: Gradual Rollout
- [ ] Enable for 10% of users
- [ ] Monitor error rates
- [ ] Increase to 50% if stable
- [ ] Full rollout

### Phase 4: Deprecation
- [ ] Remove feature flag
- [ ] Delete old editor code
- [ ] Update documentation

## Rollback Plan

If issues arise:

1. **Quick Rollback**: Set `NEXT_PUBLIC_USE_TIPTAP_EDITOR=false`
2. **Per-User Rollback**: Users can disable via localStorage
3. **Full Rollback**: Remove new editor, keep old as default

Old editor remains available during entire migration.

## Common Issues

### Issue: Templates Look Different

**Cause**: Visual representation changed (badges vs raw syntax)
**Solution**: This is intentional - WYSIWYG design. Templates serialize identically.

### Issue: Can't Type Brackets

**Cause**: Variables/colors are inserted as nodes, not typed
**Solution**: Use VariablePicker to insert templates features. This prevents syntax errors.

### Issue: Line Length Differs

**Cause**: Calculation might differ from backend
**Solution**: Verify length-calculator.ts matches src/templates/engine.py logic

### Issue: Drag & Drop Not Working

**Cause**: Browser compatibility or React Strict Mode
**Solution**: Check TipTap drag extension is loaded

## Support

- Documentation: `/web/src/components/tiptap-template-editor/README.md`
- Tests: `/web/src/__tests__/tiptap-*.test.ts`
- Examples: See page-builder.tsx integration

## Timeline

Recommended migration timeline:

- **Week 1**: Development testing, fix bugs
- **Week 2**: Beta testing with admin users
- **Week 3-4**: Gradual rollout (10% → 50% → 100%)
- **Week 5**: Monitor stability
- **Week 6+**: Remove old editor if stable

## Checklist

Before enabling for production:

- [ ] All tests passing
- [ ] Serialization verified identical
- [ ] Character counting matches backend
- [ ] Drag & drop working
- [ ] Variable picker integration working
- [ ] Alignment controls working
- [ ] Color tiles display correctly
- [ ] Symbols show actual board characters
- [ ] Mobile responsive
- [ ] Accessibility (keyboard navigation)
- [ ] Documentation updated
- [ ] Rollback plan tested
