# Frontend Redesign Plan: TradingView-Inspired Theme

## Goal
Transform the frontend from "FAST Chat" to "Stock Market Data" with a TradingView-inspired look and feel.

## TradingView Design Characteristics
1. **Dark theme by default** - Professional trading interface
2. **Color scheme**: 
   - Background: Very dark blue/black (#131722, #1E222D)
   - Accent: Bright blue (#2962FF)
   - Success/Buy: Green (#089981)
   - Danger/Sell: Red (#F23645)
   - Text: Light gray/white on dark
3. **Typography**: Clean, professional sans-serif
4. **Layout**: Dense information, efficient use of space
5. **Charts**: Prominent, professional financial charts
6. **Icons**: Line-style, minimal, professional

## Changes to Implement

### 1. Branding
- Change "FAST Chat" → "Stock Market Data"
- Update logo from "F" to stock chart icon or "SMD"
- Update welcome message to emphasize market data and trading

### 2. Color Scheme (globals.css)
- Primary background: Dark blue-black (#131722)
- Secondary background: Slightly lighter (#1E222D)
- Accent color: Bright blue (#2962FF)
- Success: Green (#089981)
- Danger: Red (#F23645)
- Border: Subtle dark borders
- Remove gradient backgrounds, use solid dark colors

### 3. Header (ChatHeader.tsx)
- Dark background with subtle border
- Stock chart icon instead of "F"
- Professional button styling
- Market-themed colors

### 4. Chat Interface (ChatInterface.tsx)
- Update welcome message
- Change suggested prompts to market-focused
- Dark theme throughout
- Professional spacing

### 5. Typography & Spacing
- Tighter spacing for information density
- Professional font weights
- Clear hierarchy

## Files to Modify
1. `frontend/src/styles/globals.css` - Color scheme and theme
2. `frontend/src/components/chat/ChatHeader.tsx` - Title and logo
3. `frontend/src/components/chat/ChatInterface.tsx` - Welcome message and prompts

## Implementation Steps
1. Update globals.css with TradingView color palette
2. Change branding text in ChatHeader
3. Update welcome message and prompts in ChatInterface
4. Test dark theme appearance
5. Verify all components look professional

## Color Reference
```css
/* TradingView-inspired palette */
--tv-background-primary: #131722;
--tv-background-secondary: #1E222D;
--tv-background-tertiary: #2A2E39;
--tv-accent-blue: #2962FF;
--tv-success-green: #089981;
--tv-danger-red: #F23645;
--tv-text-primary: #D1D4DC;
--tv-text-secondary: #787B86;
--tv-border: #2A2E39;
```
