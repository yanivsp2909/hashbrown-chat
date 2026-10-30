---
name: Hashbrown Chat
description: Fry Station. A night-shift snack-bar kitchen run by a potato; whatever needs you hangs on a ticket rail.
colors:
  golden-crisp: "#f5b432"
  golden-crisp-hover: "#ffc54d"
  golden-ink: "#2a1904"
  ketchup: "#ff6f5b"
  pickle: "#9ad66f"
  mustard: "#cbb85a"
  lavender: "#bba9ff"
  turnip: "#ff8fc8"
  crisp-edge: "#d9a483"
  roast-ground: "#1a120c"
  roast-deep: "#120c08"
  fryer-panel: "#241911"
  fryer-panel-2: "#2e2017"
  fryer-panel-3: "#3a2a1e"
  crust: "#3b2512"
  crust-line: "#6a4321"
  line: "#45321f"
  line-soft: "#33241a"
  text: "#f6eadb"
  text-2: "#dcc6ae"
  muted: "#b39a82"
  ticket-paper: "#f8f0e3"
  ticket-ink: "#2b1d12"
  ticket-muted: "#6f5844"
  bun-ground: "#e9cfa5"
  bun-panel: "#f5e4c8"
  bun-text: "#2a1a0f"
  bun-gold: "#e9a21d"
typography:
  display:
    fontFamily: "ui-rounded, \"SF Pro Rounded\", system-ui, -apple-system, \"Segoe UI\", Roboto, \"Noto Sans Hebrew\", Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "ui-rounded, \"SF Pro Rounded\", system-ui, -apple-system, \"Segoe UI\", Roboto, \"Noto Sans Hebrew\", Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 800
    letterSpacing: "-0.015em"
  title:
    fontFamily: "ui-rounded, \"SF Pro Rounded\", system-ui, -apple-system, \"Segoe UI\", Roboto, \"Noto Sans Hebrew\", Arial, sans-serif"
    fontSize: "19px"
    fontWeight: 750
    letterSpacing: "-0.01em"
  body:
    fontFamily: "ui-rounded, \"SF Pro Rounded\", system-ui, -apple-system, \"Segoe UI\", Roboto, \"Noto Sans Hebrew\", Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "ui-rounded, \"SF Pro Rounded\", system-ui, -apple-system, \"Segoe UI\", Roboto, \"Noto Sans Hebrew\", Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 600
  score:
    fontFamily: "ui-rounded, \"SF Pro Rounded\", system-ui, -apple-system, \"Segoe UI\", Roboto, \"Noto Sans Hebrew\", Arial, sans-serif"
    fontSize: "40px"
    fontWeight: 850
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontFeature: "\"tnum\""
  mono:
    fontFamily: "ui-monospace, \"SF Mono\", Menlo, Consolas, \"Liberation Mono\", monospace"
    fontSize: "12.5px"
    lineHeight: 1.55
rounded:
  ticket: "4px 4px 10px 10px"
  tile: "8px"
  sm: "9px"
  md: "14px"
  board: "16px"
  plate: "18px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "18px"
  xl: "22px"
components:
  button-primary:
    backgroundColor: "{colors.golden-crisp}"
    textColor: "{colors.golden-ink}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.golden-crisp-hover}"
    textColor: "{colors.golden-ink}"
  button-primary-disabled:
    backgroundColor: "{colors.fryer-panel-3}"
    textColor: "{colors.muted}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-2}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "40px"
  icon-button:
    backgroundColor: "{colors.fryer-panel-2}"
    textColor: "{colors.text}"
    rounded: "50%"
    size: "40px"
  input:
    backgroundColor: "{colors.roast-deep}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "44px"
  ticket:
    backgroundColor: "{colors.ticket-paper}"
    textColor: "{colors.ticket-ink}"
    rounded: "{rounded.ticket}"
    padding: "18px 14px 14px"
    width: "236px"
  side-card:
    backgroundColor: "{colors.crust}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "14px"
  turn-pill-lit:
    backgroundColor: "{colors.golden-crisp}"
    textColor: "{colors.golden-ink}"
    rounded: "{rounded.pill}"
    padding: "5px 12px"
  notice-event:
    textColor: "{colors.mustard}"
    rounded: "12px"
    padding: "8px 12px"
  notice-error:
    textColor: "{colors.ketchup}"
    rounded: "12px"
    padding: "8px 12px"
  board-plate:
    width: "348px"
---

# Design System: Hashbrown Chat

## Overview

**Creative North Star: "Fry Station"**

A night-shift snack-bar kitchen run by a potato. The shell is roasted and warm (deep brown ground, crust-brown cards, fryer-oil neutrals), deliberately not the gray-plus-blurple chat default. Anything that needs the user (a challenge, a live match, a Wordle in progress) hangs on a ticket rail across the top of the chat as a paper order ticket clipped to a bar; finished games stamp the ticket WON, LOST or DRAW.

Density is chat-dense but friendly: rounded system type, pill buttons, soft shadows. Dark is the default and required; a light "bun" theme keeps every role and swaps only values.

**Key Characteristics:**
- Gold means "you can press this" and nothing else.
- Semantic sauces: mustard events, ketchup errors and losses, pickle money, lavender private.
- Paper order tickets with a crust-coloured clip, used for the login card and every rail item.
- Every game board sits on one fixed 348px plate.
- System rounded sans only; tabular figures for every number.

## Colors

Roasted browns carry the surface; a small set of condiment colours carries meaning.

### Primary
- **Golden Crisp** (golden-crisp; hover golden-crisp-hover; ink golden-ink): primary buttons, links, focus rings, selection, your-turn pill, lit tickets, clickable board cells (tic-tac-toe ring, Damka target dots and selection), the new-messages pill, the drop zone. Light theme uses bun-gold.

### Secondary (semantic sauces)
- **Mustard**: event notices.
- **Ketchup**: errors, login error, math lock-out, lost state.
- **Pickle**: token and money notices.
- **Lavender**: private messages; the inset ring on an unseen DM stays lit until noticed.
- **Turnip**: defined in both themes as a spare semantic accent; not yet assigned to a role.

Each sauce has a matching tint at 8-14% alpha for its notice background (sidecar).

### Tertiary
- **Crisp Edge**: Hashbrown's name and room dividers; the mascot's own colour, not an action.
- **Name palette** (n0-n7, sidecar): eight per-user name colours in chat, hashed per user.

### Neutral
- **Roast Ground / Roast Deep**: app background; fields, code blocks and empty tiles sink to Roast Deep.
- **Fryer Panel 1-3**: sidebar and game panel, popovers and cells, raised selections and disabled buttons.
- **Crust / Crust Line**: sidebar room card, Hashbrown's message card, the ticket clip.
- **Line / Line Soft**: borders and column dividers.
- **Text / Text 2 / Muted**: primary text, secondary text, timestamps and hints.
- **Ticket Paper / Ink / Muted**: the paper of tickets and the login card, which stay light in both themes.

### Named Rules
**The Gold Is For Pressing Rule.** Golden Crisp appears only on things the user can act on, or on the state that asks them to act (your turn, a lit ticket). Never use it for decoration, headings or status.

**The Sauce Rule.** Mustard means an event, ketchup means an error or a loss, pickle means money, lavender means private. A colour never takes on a second meaning.

**The Game Semantics Exception.** Wordle green/yellow/gray tiles, Damka red and blue pieces, the wood board and the stamp inks follow game convention and are defined locally in the game stylesheet. Wordle yellow is a game result, not the gold action colour, and must never be swapped for it.

## Typography

**Display Font:** system rounded sans (ui-rounded, SF Pro Rounded, then system-ui through Noto Sans Hebrew and Arial)
**Label/Mono Font:** ui-monospace stack for command usage, help/board dumps and ticket numbers

**Character:** Soft, round and heavy where it matters (800-850 for headings and scores), plain 400 for chat. Emoji fallbacks are appended to both stacks.

### Hierarchy
- **Display** (800, 30px, 1.1): login and closed-room card titles only.
- **Headline** (800, 20px): game card title; empty-state title steps down to 18px.
- **Title** (750, 17-19px): brand, room title, chat header room name; ticket titles at 800 15px.
- **Body** (400, 15px, 1.5; 16px under 760px): chat lines, notices at 14px. Lines cap at 78ch.
- **Label** (600-700, 13px): field labels, sidebar section titles, hints.
- **Score** (850, 40px, tabular): math duel scores; the question uses clamp(30px, 8vw, 44px).

### Named Rules
**The System Type Rule.** No downloaded or web fonts (a PRODUCT.md constraint: no CDNs, strict CSP). Rounded comes from ui-rounded where the OS has it, plain system sans elsewhere.

**The Tabular Figures Rule.** Times, scores, file sizes, coordinates and ticket numbers all use tabular numerals.

## Layout

Desktop is a three-column grid: sidebar 280px, chat fluid, game panel 384px (the contract planned 260/380; the build's 280/384 is accepted). At 1180px and below the columns become 248px / fluid and the game panel turns into a right-hand drawer (min(400px, 100%)) opened from a "Game" button. At 760px and below it is one column and the sidebar becomes a left drawer (min(300px, 86vw)) behind a scrim. Body text steps up to 16px on phones.

The ticket rail is a horizontal, scroll-snapped strip above the messages with its rail line drawn at 7px. Tickets are 236px wide (196px on phones). Spacing rhythm is 4 / 8 / 12 / 18 / 22: 18px column gutters, 22px between sidebar and game-panel groups.

**The One Plate Rule.** Every board (tic-tac-toe, Damka, math duel) sits on a square plate of min(348px, 100%). The Wordle grid, letter tray and guess form share that same 348px width, so stacked match and Wordle cards line up on one edge.

## Elevation & Depth

Depth is a mix of tonal layers (ground, then panel, then panel-2/3) and two soft ambient shadows. Shadows lift paper and floating things; panels stay flat and are divided by hairlines.

### Shadow Vocabulary
- **Resting lift** (shadow-1): Hashbrown's card, the selected segmented tab, the Damka board.
- **Floating** (shadow-2): login ticket, popovers, drawers, new-messages pill.
- **Ticket hang** (two-layer, sidecar): rail tickets; a lit ticket adds a 3px gold ring in front.

**The Paper Floats Rule.** Only paper (tickets, the login card) and transient surfaces (popovers, drawers) cast a strong shadow. Panels never do.

## Shapes

Pills (999px) for buttons, the segmented control, the composer input and the turn pill; circles for icon buttons and Damka pieces. Cards and popovers use 14px; fields 9px; notices and chat lines 10-12px; board cells 16px; plates and empty states 18px. Tickets have tight 4px tops and 10px bottoms (14px on the login card), hung from a 46x12px crust-coloured clip. Empty states use a 2px dashed border; the ticket and login foot use a dashed tear line.

## Components

### Buttons
- **Shape:** pill (999px), 40px tall, 650 weight; presses scale to 0.97.
- **Primary:** Golden Crisp on golden ink with a small drop shadow; gets a darker gold border in the light theme.
- **Hover / Focus:** hover brightens to golden-crisp-hover (only on fine pointers); focus shows a 2px gold outline offset by 2px.
- **Ghost:** transparent with a line border and text-2; on hover the border turns gold-ring.
- **Icon button:** a 40px circle on panel-2 with inline SVG strokes at 18px.

### Inputs / Fields
- **Style:** Roast Deep fill, 1px line border, 9px radius, 44px tall; the composer input is a 46px pill.
- **Focus:** gold border plus a 3px gold-soft halo.
- **Error:** a ketchup-tinted block under the form, never a red border alone.

### Order Ticket (signature)
Paper card hung from a clip, with a title, a mono ticket number, muted lines and compact 34px actions. A pending invite shows its exact 180 s as a draining bar that turns red when low. The result stamp is rotated -10deg, uppercase 900 weight and multiply-blended, in won-green, lost-red or draw-brown.

### Notices
Rounded 12px tinted strips in chat, using the Sauce Rule colours. System lines are muted and indented to the text column. Help and board dumps are mono on a panel with a soft border.

### Game Boards
Tic-tac-toe cells are panel-2 with a gold-ring border while playable. Damka is a wood board (light #e7cfa6, dark #8b5a33) with a 3px brown frame. Wordle tiles are 8px squares that flip in row by row.

## Do's and Don'ts

### Do:
- **Do** reserve Golden Crisp for actions and your-turn states.
- **Do** keep sauce colours to their single meanings, with their soft tint for backgrounds.
- **Do** put any new board on the 348px plate.
- **Do** use tabular figures for every number.
- **Do** give every motion a reduced-motion fallback (fade or 1ms).

### Don't:
- **Don't** load web fonts or use CDNs.
- **Don't** use gold for headings, dividers, decoration or status.
- **Don't** recolour Wordle yellow to the action gold, or the action gold to Wordle yellow.
- **Don't** add shadows to the sidebar, chat column or game panel.
