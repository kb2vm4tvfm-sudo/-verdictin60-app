"""Library tab construction, moved from app.py (Phase 8 refactor, no behavior change).

``build_library_tab(app, parent)`` builds the widget exactly as the former
``App._build_library_tab`` method did — it delegates to the existing
``case_library.LibraryTab`` widget.
"""
import case_library


def build_library_tab(app, parent):
    app._lib_tab = case_library.LibraryTab(parent, app._library)
