# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import zipfile
import json
import os
import re

ADDON_ID   = 'plugin.video.fenskeleton'
SKIN_ID    = 'skin.fenmage'
try:
	ADDON = xbmcaddon.Addon(ADDON_ID)
	ADDON_PATH = ADDON.getAddonInfo('path')
except Exception:
	# Some skin-launched RunScript calls have no normal addon context.
	# Use this file location so the rebuild tool still works on Android boxes.
	ADDON = None
	ADDON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

# ---------------------------------------------------------------------------
# Plugin URL builder
# ---------------------------------------------------------------------------

def _addon_icon(filename):
	return 'special://home/addons/plugin.video.fenskeleton/resources/media/icons/%s' % filename

def _plugin(mode, **kwargs):
	url = 'plugin://plugin.video.fenskeleton/?mode=%s' % mode
	for k, v in kwargs.items():
		url += '&%s=%s' % (k, v)
	return url

# ---------------------------------------------------------------------------
# XML templates
# ---------------------------------------------------------------------------
_WIDGET_ITEM = '''\
        <include content="{ctype}">
            <param name="content_path" value="{path}"/>
            <param name="widget_header" value="{header}"/>
            <param name="widget_target" value="videos"/>
            <param name="list_id" value="{lid}"/>
        </include>'''

_WIDGET_FILE = '''\
<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="{include_name}">
        <definition>
{rows}
        </definition>
    </include>
</includes>'''

_MENU_FILE = '''\
<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="{include_name}">
        <item>
            <label>{label}</label>
            <onclick>ActivateWindow(Videos,{path},return)</onclick>
            <property name="menu_id">$NUMBER[{menu_id}]</property>
            <thumb>{thumb}</thumb>
            <property name="id">{item_id}</property>
            <visible>!Skin.HasSetting({hide_setting})</visible>
        </item>
    </include>
</includes>'''

# ---------------------------------------------------------------------------
# Default XML definitions
# ---------------------------------------------------------------------------

# Main-menu items — what the left nav bar shows for each panel button
_DEFAULT_MENUS = [
	{
		'file':         'script-fenmage-main_menu_movies.xml',
		'include_name': 'MoviesMainMenu',
		'label':        'Movies',
		'path':         _plugin('navigator.main', action='MovieList'),
		'menu_id':      '19000',
		'thumb':        _addon_icon('movies.png'),
		'item_id':      'movies',
		'hide_setting': 'HomeMenuNoMoviesButton',
	},
	{
		'file':         'script-fenmage-main_menu_tvshows.xml',
		'include_name': 'TVShowsMainMenu',
		'label':        'TV Shows',
		'path':         _plugin('navigator.main', action='TVShowList'),
		'menu_id':      '22000',
		'thumb':        _addon_icon('tv.png'),
		'item_id':      'tvshows',
		'hide_setting': 'HomeMenuNoTVShowsButton',
	},
	{
		'file':         'script-fenmage-main_menu_custom1.xml',
		'include_name': 'Custom1MainMenu',
		'label':        'Anime',
		'path':         _plugin('navigator.main', action='AnimeList'),
		'menu_id':      '23000',
		'thumb':        _addon_icon('anime.png'),
		'item_id':      'custom1',
		'hide_setting': 'HomeMenuNoCustom1Button',
	},
	{
		'file':         'script-fenmage-main_menu_custom2.xml',
		'include_name': 'Custom2MainMenu',
		'label':        'My Lists',
		'path':         _plugin('navigator.my_content'),
		'menu_id':      '24000',
		'thumb':        _addon_icon('lists.png'),
		'item_id':      'custom2',
		'hide_setting': 'HomeMenuNoCustom2Button',
	},
	{
		'file':         'script-fenmage-main_menu_custom3.xml',
		'include_name': 'Custom3MainMenu',
		'label':        'Search',
		'path':         _plugin('navigator.search'),
		'menu_id':      '25000',
		'thumb':        _addon_icon('search.png'),
		'item_id':      'custom3',
		'hide_setting': 'HomeMenuNoCustom3Button',
	},
]

# Widget panels — what appears on the right when a nav button is focused.
# Each entry is a list of widget rows; list_ids must be unique across all panels.
_DEFAULT_WIDGETS = [
	{
		'file':         'script-fenmage-widget_movies.xml',
		'include_name': 'MovieWidgets',
		'rows': [
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_movie_list', action='tmdb_movies_popular'),        'header': 'Popular Movies',      'lid': '10001'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_movie_list', action='tmdb_movies_blockbusters'),   'header': 'Blockbusters',        'lid': '10002'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_movie_list', action='tmdb_movies_in_theaters'),    'header': 'In Theaters',         'lid': '10003'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_movie_list', action='tmdb_movies_latest_releases'),'header': 'Latest Releases',     'lid': '10004'},
			{'ctype': 'WidgetListLandscape', 'path': _plugin('build_movie_list', action='tmdb_movies_upcoming'),       'header': 'Upcoming Movies',     'lid': '10005'},
			# local library genre / studio tiles (only visible when library is populated)
			{'ctype': 'WidgetListCategory',
			 'path': 'videodb://movies/genres/',
			 'header': 'Browse by Genre',   'lid': '19900'},
			{'ctype': 'WidgetListCategory',
			 'path': 'videodb://movies/studios/',
			 'header': 'Studios',           'lid': '19800'},
		],
	},
	{
		'file':         'script-fenmage-widget_tvshows.xml',
		'include_name': 'TVShowWidgets',
		'rows': [
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_tvshow_list', action='tmdb_tv_popular'),           'header': 'Popular TV Shows',    'lid': '20001'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_tvshow_list', action='tmdb_tv_on_the_air'),        'header': 'On The Air',          'lid': '20002'},
			{'ctype': 'WidgetListLandscape', 'path': _plugin('build_in_progress_episode'),                             'header': 'Continue Watching',   'lid': '20003'},
			{'ctype': 'WidgetListLandscape', 'path': _plugin('navigator.random_next_up_widget'),                             'header': 'Random Next Episodes','lid': '20005'},
			{'ctype': 'WidgetListLandscape', 'path': _plugin('build_next_episode'),                                    'header': 'Next Episodes',       'lid': '20004'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_tvshow_list', action='tmdb_tv_airing_today'),     'header': 'Airing Today',        'lid': '20006'},
			# local library tiles
			{'ctype': 'WidgetListCategory',
			 'path': 'videodb://tvshows/genres/',
			 'header': 'Browse by Genre',   'lid': '22900'},
			{'ctype': 'WidgetListCategory',
			 'path': 'videodb://tvshows/studios/',
			 'header': 'Networks',          'lid': '22800'},
		],
	},
	{
		'file':         'script-fenmage-widget_custom1.xml',
		'include_name': 'Custom1Widgets',
		'rows': [
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_tvshow_list', action='tmdb_anime_popular'),        'header': 'Popular Anime',       'lid': '30001'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_tvshow_list', action='tmdb_anime_popular'),        'header': 'Popular Anime',       'lid': '30002'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_tvshow_list', action='tmdb_anime_premieres'),      'header': 'New Anime',           'lid': '30003'},
			{'ctype': 'WidgetListLandscape', 'path': _plugin('build_tvshow_list', action='tmdb_anime_premieres'),      'header': 'Anime Premieres',     'lid': '30004'},
		],
	},
	{
		'file':         'script-fenmage-widget_custom2.xml',
		'include_name': 'Custom2Widgets',
		'rows': [
			{'ctype': 'WidgetListLandscape', 'path': _plugin('build_in_progress_episode'),                            'header': 'In Progress Episodes','lid': '40001'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_movie_list',  action='in_progress_movies'),       'header': 'In Progress Movies',  'lid': '40002'},
			{'ctype': 'WidgetListLandscape', 'path': _plugin('build_movie_list',  action='recent_watched_movies'),    'header': 'Recently Watched',    'lid': '40003'},
			{'ctype': 'WidgetListLandscape', 'path': _plugin('build_next_episode'),                                   'header': 'Next Episodes',       'lid': '40004'},
			{'ctype': 'WidgetListLandscape', 'path': _plugin('navigator.random_next_up_widget'),                            'header': 'Random Next Episodes','lid': '40005'},
		],
	},
	{
		'file':         'script-fenmage-widget_custom3.xml',
		'include_name': 'Custom3Widgets',
		'rows': [
			{'ctype': 'WidgetListPoster',    'path': _plugin('navigator.random_lists'),                               'header': 'Random Lists',        'lid': '50001'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_movie_list', action='tmdb_movies_premieres'),     'header': 'Premieres',           'lid': '50002'},
			{'ctype': 'WidgetListPoster',    'path': _plugin('build_tvshow_list', action='tmdb_tv_premieres'),        'header': 'TV Premieres',        'lid': '50003'},
		],
	},
]

# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _skin_xml_path(filename):
	return xbmcvfs.translatePath(
		'special://home/addons/%s/xml/%s' % (SKIN_ID, filename)
	)

def _file_is_stub(path):
	"""Return True if the file contains an empty <definition/> stub."""
	try:
		fh = xbmcvfs.File(path, 'r')
		content = fh.read()
		fh.close()
		return '<definition/>' in content or '<definition />' in content
	except Exception:
		return True   # missing → treat as stub

def _write_file(path, content):
	fh = xbmcvfs.File(path, 'w')
	fh.write(content)
	fh.close()

# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def ensure_default_xmls(force=False):
	"""
	Write default widget and main-menu XML files into the skin's xml/ folder.
	Only writes files that still contain the empty <definition/> stub shipped
	with the skin bundle — user customisations are left untouched.
	Reloads the skin if any files were written so changes take effect immediately.
	"""
	wrote_any = False

	# Main-menu items
	for cfg in _DEFAULT_MENUS:
		dest = _skin_xml_path(cfg['file'])
		if not force and not _file_is_stub(dest):
			continue
		xml = _MENU_FILE.format(**cfg)
		_write_file(dest, xml)
		xbmc.log('FenSkeleton: wrote %s' % cfg['file'], xbmc.LOGINFO)
		wrote_any = True

	# Widget panels
	for panel in _DEFAULT_WIDGETS:
		dest = _skin_xml_path(panel['file'])
		if not force and not _file_is_stub(dest):
			continue
		rows_xml = '\n'.join(
			_WIDGET_ITEM.format(**row) for row in panel['rows']
		)
		xml = _WIDGET_FILE.format(
			include_name=panel['include_name'],
			rows=rows_xml,
		)
		_write_file(dest, xml)
		xbmc.log('FenSkeleton: wrote %s' % panel['file'], xbmc.LOGINFO)
		wrote_any = True

	if wrote_any:
		xbmc.log('FenSkeleton: skin XMLs written — reloading skin', xbmc.LOGINFO)
		import xbmc as _xbmc
		_xbmc.executebuiltin('ReloadSkin()')


# ---------------------------------------------------------------------------
# Skin install / DB helpers (unchanged from original)
# ---------------------------------------------------------------------------

def is_installed(addon_id):
	return xbmcvfs.exists(
		xbmcvfs.translatePath('special://home/addons/%s/' % addon_id)
	)


def install_skin():
	import glob
	bundles  = xbmcvfs.translatePath(os.path.join(ADDON_PATH, 'resources', 'bundles'))
	addons   = xbmcvfs.translatePath('special://home/addons/')
	matches  = sorted(glob.glob(os.path.join(bundles, 'skin.fenmage-*.zip')))
	if not matches:
		xbmc.log('FenSkeleton: no skin bundle found in %s' % bundles, xbmc.LOGERROR)
		return False
	zip_path = matches[-1]
	try:
		with zipfile.ZipFile(zip_path, 'r') as z:
			z.extractall(addons)
		_write_skin_marker(bundled_skin_version())
		xbmc.log('FenSkeleton: skin extracted successfully', xbmc.LOGINFO)
		return True
	except Exception as e:
		xbmc.log('FenSkeleton: skin extract failed: %s' % str(e), xbmc.LOGERROR)
		return False


def force_enable_in_db(addon_id):
	import sqlite3 as _sql
	import glob
	db_dir   = xbmcvfs.translatePath('special://database/')
	matches  = sorted(glob.glob(os.path.join(db_dir, 'Addons*.db')), reverse=True)
	if not matches:
		return False
	try:
		conn = _sql.connect(matches[0], timeout=10)
		cur  = conn.cursor()
		cur.execute(
			'UPDATE installed SET enabled=1, disabledReason=0 WHERE addonID=?',
			(addon_id,)
		)
		if cur.rowcount == 0:
			cur.execute(
				'INSERT OR REPLACE INTO installed (addonID, enabled, origin, disabledReason) '
				'VALUES (?, 1, \'\', 0)',
				(addon_id,)
			)
		conn.commit()
		conn.close()
		return True
	except Exception as e:
		xbmc.log('FenSkeleton: DB enable failed for %s: %s' % (addon_id, str(e)), xbmc.LOGERROR)
		return False


def enable_addon(addon_id, monitor):
	xbmc.executebuiltin('UpdateLocalAddons')
	monitor.waitForAbort(4)
	force_enable_in_db(addon_id)
	payload = json.dumps({
		'jsonrpc': '2.0',
		'method': 'Addons.SetAddonEnabled',
		'params': {'addonid': addon_id, 'enabled': True},
		'id': 1
	})
	xbmc.executeJSONRPC(payload)
	monitor.waitForAbort(1)


def switch_skin(monitor):
	monitor.waitForAbort(2)
	xbmc.executeJSONRPC(json.dumps({
		'jsonrpc': '2.0', 'method': 'Settings.SetSettingValue',
		'params': {'setting': 'lookandfeel.skin', 'value': 'skin.estuary'}, 'id': 1
	}))
	monitor.waitForAbort(3)
	xbmc.executeJSONRPC(json.dumps({
		'jsonrpc': '2.0', 'method': 'Settings.SetSettingValue',
		'params': {'setting': 'lookandfeel.skin', 'value': SKIN_ID}, 'id': 1
	}))
	monitor.waitForAbort(4)
	xbmc.executebuiltin('SendClick(10131, 11)')


def pre_set_skin_firsttimerun():
	settings_dir  = xbmcvfs.translatePath('special://profile/addon_data/skin.fenmage/')
	settings_file = os.path.join(settings_dir, 'settings.xml')
	BOOL_TRUE     = '<setting id="firsttimerun" type="bool">true</setting>'
	try:
		if not xbmcvfs.exists(settings_dir):
			xbmcvfs.mkdirs(settings_dir)
		existing = ''
		if xbmcvfs.exists(settings_file):
			fh = xbmcvfs.File(settings_file, 'r')
			existing = fh.read()
			fh.close()
		if BOOL_TRUE in existing:
			return
		cleaned = re.sub(
			r'\s*<setting[^>]*id=["\']firsttimerun["\'][^>]*>.*?</setting>',
			'', existing, flags=re.DOTALL
		)
		if '<settings>' in cleaned:
			updated = cleaned.replace('<settings>', '<settings>\n    ' + BOOL_TRUE)
		else:
			updated = (
				'<?xml version="1.0" encoding="utf-8"?>\n'
				'<settings>\n    ' + BOOL_TRUE + '\n</settings>\n'
			)
		fh = xbmcvfs.File(settings_file, 'w')
		fh.write(updated)
		fh.close()
	except Exception as e:
		xbmc.log('FenSkeleton: firsttimerun write error: %s' % str(e), xbmc.LOGWARNING)



def _version_tuple(v):
	try:
		return tuple(int(x) for x in re.findall(r'\d+', v)[:4])
	except Exception:
		return (0,)

def bundled_skin_version():
	import glob
	bundles = xbmcvfs.translatePath(os.path.join(ADDON_PATH, 'resources', 'bundles'))
	matches = sorted(glob.glob(os.path.join(bundles, 'skin.fenmage-*.zip')))
	if not matches:
		return '0'
	m = re.search(r'skin\.fenmage-([0-9.]+)\.zip$', matches[-1])
	return m.group(1) if m else '0'

def installed_skin_version():
	try:
		return xbmcaddon.Addon(SKIN_ID).getAddonInfo('version')
	except Exception:
		return _read_installed_skin_version_from_xml()


def _read_installed_skin_version_from_xml():
	try:
		addon_xml = xbmcvfs.translatePath('special://home/addons/%s/addon.xml' % SKIN_ID)
		if not xbmcvfs.exists(addon_xml): return '0'
		fh = xbmcvfs.File(addon_xml, 'r')
		content = fh.read()
		fh.close()
		m = re.search(r'version=["\']([^"\']+)', content)
		return m.group(1) if m else '0'
	except Exception:
		return '0'

def _skin_marker_path():
	return xbmcvfs.translatePath('special://profile/addon_data/plugin.video.fenskeleton/skin_install_marker.txt')

def _read_skin_marker():
	try:
		path = _skin_marker_path()
		if not xbmcvfs.exists(path): return ''
		fh = xbmcvfs.File(path, 'r')
		data = fh.read().strip()
		fh.close()
		return data
	except Exception:
		return ''

def _write_skin_marker(version):
	try:
		dirname = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.fenskeleton/')
		if not xbmcvfs.exists(dirname): xbmcvfs.mkdirs(dirname)
		fh = xbmcvfs.File(_skin_marker_path(), 'w')
		fh.write(str(version))
		fh.close()
	except Exception as e:
		xbmc.log('FenSkeleton: skin marker write failed: %s' % str(e), xbmc.LOGWARNING)

def skin_needs_install_or_upgrade():
	bundled = bundled_skin_version()
	# FenSkeleton lean video-addon builds do not carry the skin zip.
	# If no bundle exists, do not keep trying to install/reinstall the skin on startup.
	if bundled in ('0', '', None):
		return False
	if not is_installed(SKIN_ID):
		return True
	installed = installed_skin_version()
	if _version_tuple(installed) >= _version_tuple(bundled):
		_write_skin_marker(bundled)
		return False
	# Cheap Android boxes sometimes report version 0 during startup.
	# If the folder exists and our marker matches, do not reinstall every boot.
	if _read_skin_marker() == bundled:
		return False
	return True

# ---------------------------------------------------------------------------
# Service entry point
# ---------------------------------------------------------------------------

def run_service():
	monitor = xbmc.Monitor()

	if skin_needs_install_or_upgrade():
		if install_skin():
			enable_addon(SKIN_ID, monitor)
			if xbmcgui.Dialog().yesno(
				'FenSkeleton',
				'Fen-Mage skin installed/updated.\n\nSwitch to it now for the best experience?'
			):
				pre_set_skin_firsttimerun()
				switch_skin(monitor)

	# Populate empty skin XML stubs with default FenSkeleton content
	try:
		ensure_default_xmls()
	except Exception as e:
		xbmc.log('FenSkeleton: ensure_default_xmls error: %s' % str(e), xbmc.LOGWARNING)

	try:
		from caches.base_cache import make_databases
		make_databases()
	except Exception as e:
		xbmc.log('FenSkeleton: make_databases error: %s' % str(e), xbmc.LOGWARNING)

	try:
		from caches.settings_cache import sync_settings, _set_coco_defaults
		sync_settings({'silent': 'true'})
		_set_coco_defaults()
	except Exception as e:
		xbmc.log('FenSkeleton: settings warmup error: %s' % str(e), xbmc.LOGWARNING)

	try:
		from modules.settings import auto_start_fenskeleton
		from modules import kodi_utils
		if auto_start_fenskeleton():
			kodi_utils.run_addon()
	except Exception as e:
		xbmc.log('FenSkeleton: auto-start error: %s' % str(e), xbmc.LOGWARNING)

	del monitor


if __name__ == '__main__':
	run_service()

