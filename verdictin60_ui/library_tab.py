import case_library


def build_library_tab(app, parent):
    app._lib_tab = case_library.LibraryTab(parent, app._library)
