# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Plain static HTML, CSS and ES modules served by `web/web_server.py` (Python standard library). No build step, npm, CDNs or downloaded fonts. A strict CSP is in place: no inline scripts or styles.

## Users

A group of teenage friends in Israel who already use Hashbrown Chat from the terminal. The website is for the friends who aren't technical. They open a link on the same Wi-Fi, **mostly on laptops**, and chat, play 1v1 games against each other, and poke the AI bot. The host runs the server on their Mac.

## Product Purpose

A browser client for an existing chat server: rooms and groups, a fake-token economy (daily bonus, casino, shop badges), 1v1 games (Tic-Tac-Toe, Damka/checkers, Math Duel), solo Wordle, file sending, and Hashbrown 🥔, an AI that answers in the room. Success means a friend can log in, chat and finish a game without ever typing a command they don't know.

## Positioning

A private hangout for one friend group, hosted on one kid's laptop. It has a mascot (a potato called Hashbrown), inside jokes and token bragging rights. It isn't a product with strangers on it.

## Capabilities and Constraints

- The server is authoritative and sends mostly plain English text. Only game boards come with structured `state`.
- The interface language is **English**. Chat lines can be Hebrew and must show right-to-left by themselves.
- Commands are typed with `/`. The website must make the common ones one click away and the rest discoverable.
- All server data is untrusted and is rendered as text only.
- Files are limited to 2 MB.

## Brand Commitments

- The name is "Hashbrown Chat" and the mascot is Hashbrown 🥔.
- The existing voice is playful, with lots of emojis.
- Dark mode is required.

## Product Principles

- One click beats a command: every frequent `/command` gets a button.
- Games feel like games: real boards you click, not text.
- Friendly to non-technical friends: plain words, no jargon, every error tells you what to do next.

## Accessibility & Inclusion

Keyboard usable, readable contrast in both themes, respects reduced motion, works at phone width.
