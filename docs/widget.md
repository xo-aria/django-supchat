# The widget

```django
{% load supchat %}
{% supchat %}
```

The tag renders a launcher button and the chat panel, then loads three small scripts with `defer`: `i18n.js`, `sound.js` and `supchat.js`. No conversation is created until the visitor opens the widget.

## What visitors get

| Feature | Notes |
|---|---|
| Real-time messages | Over SSE, with automatic reconnect. |
| Typing indicator | Both directions. |
| Read receipts | ✓ sent, ✓✓ read by an operator. |
| Replies | Hover or tap a message, then ↩. |
| Reactions | 👍 ❤️ 😂 😮 😢 🙏 🔥 🎉 |
| Attachments | Click 📎 or paste an image. Images open in a lightbox. |
| Emoji picker | Built in, no external assets. |
| Quick replies | `QUICK_REPLIES` chips on an empty chat. |
| Pre-chat form | `PRECHAT_FORM = True`. |
| End chat & rating | ⋮ → End chat, then a 1–5 star rating with an optional comment. |
| Transcript | ⋮ → Download, or email it to the visitor's own address. |
| Language button | The 🌐 button in the header is always visible. The choice is remembered. |
| Theme | ⋮ → Theme (auto / light / dark). |
| Sound | ⋮ → Sound on/off. Sounds are synthesized with WebAudio. |
| AI badge | Shown while the AI assistant is answering. |

On screens narrower than 520px the panel opens full screen and respects safe-area insets.

## Accessibility

- The launcher is a real button with `aria-expanded` and `aria-controls`. The panel is a labelled `dialog`.
- The message list is a `role="log"` with `aria-live="polite"`, so screen readers announce new messages.
- `Esc` closes menus, then the panel. Focus returns to the launcher.
- Every icon button has an accessible name in the current language.
- Colors were chosen for WCAG AA text contrast in both themes. Visitor bubbles use a darkened accent so white text stays readable.
- `prefers-reduced-motion` disables animations.

## Theming

Override CSS variables on `.supchat-widget`:

```css
.supchat-widget {
  --sc-accent: #10b981;        /* launcher, buttons, links */
  --sc-out: #047857;           /* visitor bubbles */
  --sc-in: #ffffff;            /* support bubbles */
  --sc-bg: #ffffff;            /* panel */
  --sc-bg2: #eef1f5;           /* message area */
  --sc-ink: #111827;
  --sc-ink2: #4b5563;
  --sc-font: "Inter", system-ui, sans-serif;
}
.supchat-widget.sc-dark { --sc-in: #1f2937; }
```

Or set `SUPCHAT["ACCENT"] = "#10b981"`.

For deeper changes, override `templates/supchat/widget.html` or the static files `supchat/supchat.css` and `supchat/supchat.js` in your project.

## JavaScript API

```js
SupchatWidget.open();
SupchatWidget.close();

document.addEventListener('supchat:open', () => {});
document.addEventListener('supchat:close', () => {});
document.addEventListener('supchat:message', (e) => console.log(e.detail)); // a message object
```

The visitor's choices are stored in `localStorage`: `supchat.lang`, `supchat.theme` and `supchat.sound`.

## Browser support

Evergreen Chrome, Edge, Firefox and Safari (2022+). The widget uses `EventSource`, `fetch`, CSS logical properties and `color-mix()`.
