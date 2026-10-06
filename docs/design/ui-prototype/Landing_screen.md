# Design System Specification

## 1. Overview & Creative North Star
### Creative North Star: "The Luminal Observatory"
This design system is built to transform complex AI market research data into a cinematic, editorial experience. It moves away from the "cluttered dashboard" trope of SaaS, instead adopting the posture of a high-end research journal curated for the future.

We achieve this through **The Luminal Observatory** concept: the UI acts as a dark lens through which vibrant data "glows." We break the standard grid-bound template by utilizing intentional asymmetry—where large editorial headers offset meticulously aligned data points—creating a sense of precision and calm authority. Every interaction should feel like a deliberate movement through a high-end physical space.

---

## 2. Colors & Surface Architecture
The color palette is rooted in deep obsidian tones, utilizing light not as a decoration, but as information.

### The Palette (Material Scale)
*   **Background:** `#131313` (Deep Obsidian)
*   **Primary (Teal):** `#a5e7ff` (Main) | `#00d2ff` (Container/Glow)
*   **Secondary (Gold):** `#e9c349` (High-Value Accents/Precision)
*   **Surface Hierarchy:** 
    *   `surface_container_lowest`: `#0e0e0e` (Deep recessed areas)
    *   `surface_container_low`: `#1c1b1b` (Secondary cards)
    *   `surface_container_high`: `#2a2a2a` (Active panels)

### The "No-Line" Rule
Standard 1px borders are strictly prohibited for defining sections. Layout boundaries must be established through **Tonal Transitions**. A section shift is signaled by moving from `surface` to `surface_container_low`. If the user cannot distinguish sections without a line, increase the vertical whitespace (e.g., `spacing-16`) rather than adding a stroke.

### Surface Hierarchy & Nesting
Treat the UI as a series of nested physical layers. 
*   **Base:** `surface_dim` (#131313).
*   **Primary Containers:** `surface_container_low` for large content blocks.
*   **Nested Cards:** `surface_container_high` for elements inside those blocks.
This creates a "milled" effect, where elements feel carved into the dark interface rather than pasted on top.

### The "Glass & Gradient" Rule
For floating elements (modals, dropdowns, hovered states), use **Glassmorphism**. Apply `surface_variant` at 40% opacity with a `backdrop-filter: blur(24px)`. 
**Signature Texture:** Main CTAs should use a subtle linear gradient from `primary` (#a5e7ff) to `primary_container` (#00d2ff) at a 135-degree angle to provide a "lit from within" glow.

---

## 3. Typography
The typography system balances the tech-forward nature of AI with the timeless authority of editorial design.

*   **Display & Headlines (Manrope):** We use Manrope for its geometric precision. `display-lg` (3.5rem) should be used sparingly for "hero" insights or high-level category titles.
*   **Body & Labels (Inter):** Inter provides the functional clarity required for market research. 
*   **Editorial Contrast:** Create a "signature" look by pairing a `display-sm` headline with a `label-sm` (all caps, 0.1rem letter spacing) immediately above it. This mimics high-end magazine mastheads.

---

## 4. Elevation & Depth

### The Layering Principle
Depth is achieved through **Tonal Stacking**. To lift a component, do not use a shadow first; use a higher surface token.
*   **Example:** A "Respondent Profile" card should be `surface_container_low`. When hovered, it transitions to `surface_container_high`.

### Ambient Shadows
Shadows must mimic natural light. Use a 32px to 64px blur radius with an opacity of 6% using the `primary` (Teal) or `surface_container_highest` color. Never use pure black or grey shadows; the shadow should feel like a faint color bleed from the element.

### The "Ghost Border" Fallback
Where accessibility requirements demand a container edge (e.g., input fields), use a **Ghost Border**. Use the `outline_variant` token at 15% opacity. It should be felt, not seen.

---

## 5. Components

### Buttons
*   **Primary:** Teal gradient (`primary` to `primary_container`), `on_primary` text, `sm` (0.125rem) roundedness. It should feel like a solid, glowing gem.
*   **Secondary:** Ghost Border style. `outline_variant` at 20% opacity with `primary` text.
*   **Tertiary:** No border, no background. `on_surface_variant` text, shifting to `primary` on hover.

### Input Fields
*   **Style:** `surface_container_lowest` background, Ghost Border (`outline_variant` @ 15%).
*   **Focus:** Border opacity increases to 100% using the `primary` (Teal) color, accompanied by a 4px soft teal outer glow.

### Cards & Lists
*   **Constraint:** Zero dividers. Use `spacing-8` (2.75rem) to separate list items.
*   **Visual Separation:** In lists, alternate background colors between `surface` and `surface_container_lowest` for row-level distinction.

### Synthetic Respondent Modules (Custom)
*   For AI-generated personas, use a "Glass Panel" with a 1px `top-only` border (Ghost Border style) to catch a "specular highlight," making the panel look like a physical sheet of glass under a spotlight.

---

## 6. Do’s and Don’ts

### Do:
*   **Do** use generous whitespace (`spacing-12` and `spacing-16`) to create a sense of luxury and "calm."
*   **Do** use `secondary` (Gold) for "Precision Data"—specific percentages, AI confidence scores, or key insights.
*   **Do** use asymmetrical layouts (e.g., a 2-column grid where the left column is 33% width and right is 66%).

### Don't:
*   **Don't** use 100% white text. Use `on_surface` (#e5e2e1) to reduce eye strain and maintain the "cinematic" feel.
*   **Don't** use traditional "Drop Shadows" with high opacity.
*   **Don't** use standard "Full" rounded corners (pills) for anything other than Chips. Stay with `sm` or `md` for a more architectural, professional look.
*   **Don't** crowd the screen. If a page feels full, it is over-designed. Remove elements until only the essential "Observation" remains.