"""VerdictIn60 design system — single source of truth for the black/crimson brand theme.

All screens should pull colors, fonts and spacing from here (directly or via the
re-exports in verdictin60_ui.widgets) instead of hardcoding hex values, so the
whole app can be re-themed from one place.

Palette: near-black surfaces, warm off-white text, and a single deep-crimson
accent reserved for active/selected state and primary actions. Status colors
(verified/needs-review/not-verified) stay semantic and are never replaced by
the brand accent.
"""

# ── Surfaces ──────────────────────────────────────────────────────────────────
BG           = "#000000"   # app background — true black
SIDEBAR_BG   = "#0b0a09"   # very dark charcoal, separated from content by BORDER
SURFACE      = "#0e0d0c"   # top bar / footer background
CARD         = "#141210"   # card / panel background — dark charcoal
CARD_ALT     = "#1a1715"   # alternating row / secondary panel background
CARD_HOVER   = "#211d1a"   # hover state for cards / rows
PANEL        = "#181513"   # panels — slightly lighter than cards
INPUT_BG     = "#1f1b18"   # text entries, textareas, secondary buttons

# ── Borders ───────────────────────────────────────────────────────────────────
BORDER       = "#2a2725"   # soft graphite
BORDER_LIGHT = "#3a3633"

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT           = "#EAE9E4"   # primary text — warm off-white (brand color)
TEXT_OFF       = "#d9d7d0"   # slightly muted primary text
TEXT_SECONDARY = "#a6a29b"   # secondary labels — muted gray
TEXT_MUTED     = "#8a8680"   # muted body text
TEXT_DIM       = "#5c5850"   # dim hints / idle placeholders
DISABLED       = "#6b675f"   # disabled control fg/bg base

# ── Accent (deep crimson, the VerdictIn60 signature color) ────────────────────
ACCENT       = "#920805"   # primary brand accent
ACCENT_HOT   = "#b30a06"   # hover state
ACCENT_DEEP  = "#6e0604"   # pressed / deep state
ACCENT_MUTED = "#2a0e0d"   # tinted accent background (badges, active nav pill)

# ── Status colors (semantic — never replaced by ACCENT) ───────────────────────
SUCCESS      = "#22c55e"   # Verified — emerald green
SUCCESS_BG   = "#12241a"
SUCCESS_HOT  = "#1a4a34"   # hover state for success-styled buttons/badges
WARNING      = "#f59e0b"   # Needs Review — amber
WARNING_BG   = "#26200c"
ERROR        = "#c2564c"   # Not Verified — muted red (distinct from ACCENT crimson)
ERROR_BG     = "#271512"

# ── Fonts ─────────────────────────────────────────────────────────────────────
FONT_FAMILY      = "Helvetica"
FONT_MONO        = "Courier"
FONT_TITLE       = (FONT_FAMILY, 20, "bold")
FONT_SECTION     = (FONT_FAMILY, 13, "bold")
FONT_LABEL       = (FONT_FAMILY, 8, "bold")
FONT_BODY        = (FONT_FAMILY, 10)
FONT_BODY_BOLD   = (FONT_FAMILY, 10, "bold")
FONT_BUTTON      = (FONT_FAMILY, 12, "bold")

# ── Spacing ───────────────────────────────────────────────────────────────────
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 36

SIDEBAR_WIDTH = 232
