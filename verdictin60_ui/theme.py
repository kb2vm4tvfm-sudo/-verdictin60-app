"""VerdictIn60 design system — single source of truth for the dark navy/cyan theme.

All screens should pull colors, fonts and spacing from here (directly or via the
re-exports in verdictin60_ui.widgets) instead of hardcoding hex values, so the
whole app can be re-themed from one place.
"""

# ── Surfaces ──────────────────────────────────────────────────────────────────
BG           = "#0a0e17"   # app background
SIDEBAR_BG   = "#0a0e17"   # sidebar background (separated from content by BORDER)
SURFACE      = "#0d1220"   # top bar / footer background
CARD         = "#101625"   # card / panel background
CARD_ALT     = "#121a2b"   # alternating row / secondary panel background
CARD_HOVER   = "#141c2e"   # hover state for cards / rows
INPUT_BG     = "#182236"   # text entries, textareas, secondary buttons

# ── Borders ───────────────────────────────────────────────────────────────────
BORDER       = "#232c40"
BORDER_LIGHT = "#333e58"

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT           = "#f8fafc"   # primary text (was WHITE)
TEXT_OFF       = "#e2e8f0"   # slightly muted primary text (was OFF_WHITE)
TEXT_SECONDARY = "#a8b3c7"   # secondary labels (was #AAAAAA)
TEXT_MUTED     = "#94a3b8"   # muted body text (was LIGHT_GRAY)
TEXT_DIM       = "#5b6578"   # dim hints / idle placeholders (was #444444)
DISABLED       = "#64748b"   # disabled control fg/bg base (was MUTED)

# ── Accent (cyan → blue, the VerdictIn60 brand color) ─────────────────────────
ACCENT       = "#38bdf8"
ACCENT_HOT   = "#0ea5e9"
ACCENT_DEEP  = "#3b82f6"
ACCENT_MUTED = "#0b3350"   # tinted accent background (badges, active nav pill)

# ── Status colors ─────────────────────────────────────────────────────────────
SUCCESS      = "#22c55e"
SUCCESS_BG   = "#0f2e1c"
WARNING      = "#f59e0b"
WARNING_BG   = "#241a0a"
ERROR        = "#f87171"
ERROR_BG     = "#2a1015"

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
