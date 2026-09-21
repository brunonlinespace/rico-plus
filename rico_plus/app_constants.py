# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared application identity and metadata."""

from rico_plus import (
    APP_ID,
    APP_NAME as SUITE_APP_NAME,
    APP_VERSION,
    DESKTOP_ID,
    PUBLISHER_ID,
)

# Visible product branding and canonical Suite/package identity are Rico Plus.
APP_INTERNAL_NAME = "rico-plus"
APP_BRAND_NAME = "Rico Plus"
APP_DISPLAY_NAME = APP_BRAND_NAME
APP_WINDOW_TITLE = APP_DISPLAY_NAME
APP_RUNTIME_DESKTOP_ID = DESKTOP_ID
APP_REVISION = "0.0.3"

ORGANIZATION_NAME = "brunonlinespace"
ORGANIZATION_DOMAIN = "github.com/brunonlinespace"

RTF_EXTENSIONS = frozenset({".rtf"})
RTF_FILE_GLOB = "*.rtf"

GITHUB_URL = "https://github.com/brunonlinespace/rico-plus"
ISSUES_URL = f"{GITHUB_URL}/issues"
