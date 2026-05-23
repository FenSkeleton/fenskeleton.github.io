# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcvfs

# from modules.logger import logger

SKIN_ID = "skin.fenmage"


def fix_black_screen():
    """
    Fixes occasional black screen on skin load by forcing a skin reload
    if the home window isn't rendering correctly.
    """
    monitor = xbmc.Monitor()
    monitor.waitForAbort(0.5)
    if not xbmc.getCondVisibility("Window.IsVisible(home)"):
        xbmc.executebuiltin("ActivateWindow(home)")
    del monitor


def modify_keymap():
    """
    Applies any custom keymap overrides for Fen-Mage.
    Runs silently on skin load — extend here for custom remote mappings.
    """
    pass


def set_image():
    """
    Opens a file browser so the user can pick a background image
    and stores it as a skin string.
    """
    dialog = xbmcgui.Dialog()
    image_path = dialog.browse(
        2,
        "Select Background Image",
        "files",
        ".jpg|.jpeg|.png|.gif",
        False,
        False,
        ""
    )
    if image_path and not image_path.endswith(("/", "\\")):
        xbmc.executebuiltin("Skin.SetString(HomeFanart.path,%s)" % image_path)
        xbmc.executebuiltin("ReloadSkin()")
