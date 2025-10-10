# DependIQ Accessibility Features

## Overview

DependIQ is committed to providing an accessible experience for all users, including those with visual impairments, color vision deficiencies, and motion sensitivity.

## Available Accessibility Features

### 🔲 High Contrast Mode

Increases visual contrast for users with low vision.

**What it does:**
- Increases border thickness to 2px
- Enhances focus indicators (3px outlines)
- Uses pure black/white colors for maximum contrast
- Meets WCAG 2.1 AAA standards (7:1 contrast ratio)

**How to enable:**
1. Go to Profile → Accessibility
2. Toggle "Enable high contrast"
3. Works with any theme

**Technical Details:**
- Applies `data-high-contrast="true"` attribute
- Overrides theme colors with high contrast values
- Light mode: Pure white background, pure black text
- Dark mode: Pure black background, pure white text

---

### 👁️ Colorblind Modes

Adjust colors for users with color vision deficiency.

#### **Protanopia (Red-Blind)**
- Affects ~1% of males
- Uses blue/orange contrasts instead of red/green
- Success: Blue (#0066CC)
- Error: Orange (#FFAA00)

#### **Deuteranopia (Green-Blind)**
- Affects ~1% of males
- Similar to protanopia adaptations
- Success: Blue (#005AB5)
- Error: Orange (#FF8C00)

#### **Tritanopia (Blue-Blind)**
- Rare (~0.001% of population)
- Uses red/turquoise contrasts
- Success: Turquoise (#00CED1)
- Error: Crimson (#DC143C)

**How to enable:**
1. Go to Profile → Accessibility
2. Select your colorblind mode from dropdown
3. Colors adjust automatically across all pages

**Technical Details:**
- Applies `data-colorblind="[mode]"` attribute
- Overrides status colors only
- Works with any theme
- Maintains semantic meaning

---

### 📐 Font Size Options

Adjust text size for better readability.

**Options:**
- **Normal**: 15px (default)
- **Large**: 17px (+13%)
- **Extra Large**: 19px (+27%)

**What it affects:**
- Base font size
- Headings scale proportionally
- Sidebar logo size
- All text elements

**How to change:**
1. Go to Profile → Accessibility
2. Select font size (Normal / Large / Extra Large)
3. Change applies immediately

**Technical Details:**
- Applies `data-font-size="[size]"` attribute
- Uses rem-based sizing for consistency
- Maintains layout proportions

---

### 🎬 Reduce Motion

Minimizes animations for users sensitive to motion.

**What it does:**
- Disables all animations
- Reduces transition times to 0.01ms
- Disables scroll behavior animations
- Prevents content flashing

**Who benefits:**
- Users with vestibular disorders
- Users prone to motion sickness
- Users with attention disorders
- Battery saving on mobile devices

**How to enable:**
1. Go to Profile → Accessibility
2. Toggle "Reduce animations"
3. All motion stops immediately

**Technical Details:**
- Applies `data-reduce-motion="true"` attribute
- Uses CSS `prefers-reduced-motion` media query
- Overrides all animation/transition durations

---

## Combining Features

All accessibility features work together:

**Example Combinations:**
- Ocean theme + High contrast + Large font
- Dark theme + Protanopia mode + Reduce motion
- System theme + Deuteranopia + Extra large font

Features are independent and can be mixed as needed.

---

## WCAG Compliance

### Standards Met

✅ **WCAG 2.1 Level AA** (Minimum)
- Text contrast ratio ≥ 4.5:1
- UI component contrast ≥ 3:1
- Focus indicators visible
- Keyboard accessible

✅ **WCAG 2.1 Level AAA** (High Contrast Mode)
- Text contrast ratio ≥ 7:1
- Enhanced focus indicators
- No content flashes
- Maximum readability

### Tested Against

- **WebAIM Contrast Checker**: All themes pass AA
- **Axe DevTools**: Zero violations detected
- **NVDA Screen Reader**: Fully compatible
- **VoiceOver**: Fully compatible

---

## Keyboard Navigation

All accessibility features are keyboard accessible:

- `Tab` - Navigate through form fields
- `Space` - Toggle checkboxes
- `Enter` - Select dropdown options
- `Arrow Keys` - Navigate radio buttons
- `Shift+Tab` - Navigate backward

---

## Testing Accessibility

### Using Our Automated Tests

```bash
# Run accessibility tests
pytest tests/test_accessibility.py -v

# Run CSS validation
pytest tests/test_accessibility_css.py -v

# Run all tests
make test
```

### Manual Testing Tools

1. **Browser DevTools**
   - Lighthouse (Accessibility audit)
   - Chrome DevTools (Accessibility pane)

2. **Screen Readers**
   - Mac: VoiceOver (`Cmd+F5`)
   - Windows: NVDA (free)

3. **Color Simulators**
   - Chrome Extension: "Colorblind - Dalton"
   - Firefox Extension: "Let's get color blind"

4. **Contrast Checkers**
   - WebAIM: https://webaim.org/resources/contrastchecker/
   - Chrome DevTools: Built-in contrast ratio display

---

## Implementation Details

### Database Schema

```python
# user_preferences table
high_contrast: Boolean (default: False)
colorblind_mode: String(20) (nullable)
font_size: String(10) (default: 'normal')
reduce_motion: Boolean (default: False)
```

### API Endpoints

**GET** `/api/user/preferences`
Returns all preferences including accessibility settings

**PUT** `/api/user/preferences`
Update one or more accessibility settings:
```json
{
  "high_contrast": true,
  "colorblind_mode": "protanopia",
  "font_size": "large",
  "reduce_motion": true
}
```

### CSS Architecture

```css
/* High contrast */
body[data-high-contrast="true"] { }

/* Colorblind modes */
body[data-colorblind="protanopia"] { }
body[data-colorblind="deuteranopia"] { }
body[data-colorblind="tritanopia"] { }

/* Font sizes */
body[data-font-size="large"] { }
body[data-font-size="xlarge"] { }

/* Reduce motion */
body[data-reduce-motion="true"] { }
```

---

## Browser Support

All accessibility features work in:
- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+
- ✅ Mobile browsers

---

## Feedback & Improvements

We continuously improve accessibility based on user feedback.

**Report Issues:**
- Email: accessibility@dependiq.com
- GitHub: Create issue with "accessibility" label

**Request Features:**
- Suggest new colorblind modes
- Request additional font sizes
- Propose new accessibility features

---

## Resources

- **WCAG 2.1**: https://www.w3.org/WAI/WCAG21/quickref/
- **WebAIM**: https://webaim.org/
- **A11Y Project**: https://www.a11yproject.com/
- **MDN Accessibility**: https://developer.mozilla.org/en-US/docs/Web/Accessibility

---

*Last Updated: 2025-11-30*
*Accessibility Level: WCAG 2.1 AA (AAA with high contrast)*
