# -*- coding: utf-8 -*-
"""
FenSkeleton Watch State Foundation

v0.0.21 local-first groundwork.
- Keeps a normalized local watch-state database.
- Keeps a rolling recent activity / repair history.
- Can seed local watch-state from the existing Trakt cache safely.
- Does not write to Trakt or Simkl.
"""
from __future__ import absolute_import

import json
import time
from datetime import datetime, timedelta
from os import path, makedirs
import sqlite3 as database

from modules import kodi_utils
from caches.base_cache import connect_database

logger = kodi_utils.logger

DB_NAME = 'watchstate.db'
RECENT_DAYS_DEFAULT = 14


def _databases_path():
	return path.join(kodi_utils.addon_profile(), 'databases')


def db_path():
	folder = _databases_path()
	if not path.exists(folder):
		try: makedirs(folder)
		except: pass
	return kodi_utils.translate_path(path.join(folder, DB_NAME))


def connect_watchstate():
	dbcon = database.connect(db_path(), timeout=20, isolation_level=None, check_same_thread=False)
	dbcon.execute('PRAGMA synchronous = OFF')
	dbcon.execute('PRAGMA journal_mode = OFF')
	return dbcon


def utc_now():
	return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')


def _safe_int(value, default=None):
	try:
		if value in (None, '', 'None'): return default
		return int(value)
	except: return default


def _parse_date(value):
	if not value: return None
	for fmt in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S'):
		try: return datetime.strptime(str(value), fmt)
		except: pass
	return None


def _recent_cutoff(days=RECENT_DAYS_DEFAULT):
	return datetime.utcnow() - timedelta(days=int(days or RECENT_DAYS_DEFAULT))


def initialize(silent=False):
	try:
		dbcon = connect_watchstate()
		dbcon.execute('''CREATE TABLE IF NOT EXISTS watch_state (
			media_type text not null,
			media_id text not null,
			season integer,
			episode integer,
			title text,
			watched integer default 0,
			progress_percent real,
			last_watched_at text,
			provider text,
			updated_at text,
			extra text,
			unique (media_type, media_id, season, episode)
		)''')
		dbcon.execute('''CREATE TABLE IF NOT EXISTS recent_activity (
			id integer primary key autoincrement,
			created_at text,
			action text,
			media_type text,
			media_id text,
			season integer,
			episode integer,
			title text,
			provider text,
			status text,
			message text,
			extra text
		)''')
		dbcon.execute('''CREATE TABLE IF NOT EXISTS provider_sync_state (
			provider text not null,
			sync_type text not null,
			last_started_at text,
			last_completed_at text,
			status text,
			message text,
			extra text,
			unique (provider, sync_type)
		)''')
		dbcon.close()
		cleanup_recent_activity(days=RECENT_DAYS_DEFAULT, silent=True)
		if not silent: kodi_utils.notification('Watch State DB Ready', 2500)
		return True
	except Exception as e:
		logger('FenSkeleton WatchState initialize failed', str(e))
		if not silent: kodi_utils.notification('Watch State DB Failed', 3000)
		return False


def record_activity(action, media_type='', media_id='', season=None, episode=None, title='', provider='local', status='ok', message='', extra=None):
	try:
		initialize(silent=True)
		dbcon = connect_watchstate()
		dbcon.execute('''INSERT INTO recent_activity
			(created_at, action, media_type, media_id, season, episode, title, provider, status, message, extra)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
			(utc_now(), action, media_type, str(media_id or ''), _safe_int(season), _safe_int(episode), title or '', provider or '', status or '', message or '', json.dumps(extra or {})))
		dbcon.close()
		return True
	except Exception as e:
		logger('FenSkeleton WatchState record_activity failed', str(e))
		return False


def cleanup_recent_activity(days=RECENT_DAYS_DEFAULT, silent=False):
	try:
		initialize(silent=True) if not path.exists(db_path()) else None
		cutoff = (datetime.utcnow() - timedelta(days=int(days or RECENT_DAYS_DEFAULT))).strftime('%Y-%m-%dT%H:%M:%S.000Z')
		dbcon = connect_watchstate()
		dbcon.execute('DELETE FROM recent_activity WHERE created_at < ?', (cutoff,))
		dbcon.execute('VACUUM')
		dbcon.close()
		if not silent: kodi_utils.notification('Watch State Activity Cleaned', 2500)
		return True
	except Exception as e:
		logger('FenSkeleton WatchState cleanup failed', str(e))
		if not silent: kodi_utils.notification('Watch State Cleanup Failed', 3000)
		return False


def upsert_watch_state(media_type, media_id, season=None, episode=None, title='', watched=0, progress_percent=None, last_watched_at='', provider='local', extra=None):
	try:
		initialize(silent=True)
		now = utc_now()
		dbcon = connect_watchstate()
		dbcon.execute('''INSERT OR REPLACE INTO watch_state
			(media_type, media_id, season, episode, title, watched, progress_percent, last_watched_at, provider, updated_at, extra)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
			(media_type, str(media_id), _safe_int(season), _safe_int(episode), title or '', int(watched or 0), progress_percent, last_watched_at or '', provider or 'local', now, json.dumps(extra or {})))
		dbcon.close()
		return True
	except Exception as e:
		logger('FenSkeleton WatchState upsert failed', str(e))
		return False


def import_trakt_cache_to_local(params=None, silent=False):
	"""Seed local watch_state from current FenSkeleton Trakt cache. Safe: local-only write."""
	try:
		initialize(silent=True)
		trakt_db = connect_database('trakt_db')
		watched_rows = trakt_db.execute('SELECT db_type, media_id, season, episode, last_played, title FROM watched').fetchall()
		progress_rows = trakt_db.execute('SELECT db_type, media_id, season, episode, resume_point, curr_time, last_played, resume_id, title FROM progress').fetchall()
		trakt_db.close()

		movies = episodes = progress = recent = 0
		cutoff = _recent_cutoff(RECENT_DAYS_DEFAULT)
		for db_type, media_id, season, episode, last_played, title in watched_rows:
			media_type = 'movie' if db_type == 'movie' else 'episode'
			if upsert_watch_state(media_type, media_id, season, episode, title, 1, None, last_played, 'trakt_import'):
				if media_type == 'movie': movies += 1
				else: episodes += 1
				played_dt = _parse_date(last_played)
				if played_dt and played_dt >= cutoff:
					recent += 1
					record_activity('watched_import', media_type, media_id, season, episode, title, 'trakt', 'ok', 'Imported recent watched item from Trakt cache')

		for db_type, media_id, season, episode, resume_point, curr_time, last_played, resume_id, title in progress_rows:
			media_type = 'movie' if db_type == 'movie' else 'episode'
			try: progress_percent = float(resume_point)
			except: progress_percent = None
			if upsert_watch_state(media_type, media_id, season, episode, title, 0, progress_percent, last_played, 'trakt_progress_import', {'curr_time': curr_time, 'resume_id': resume_id}):
				progress += 1
				played_dt = _parse_date(last_played)
				if played_dt and played_dt >= cutoff:
					recent += 1
					record_activity('progress_import', media_type, media_id, season, episode, title, 'trakt', 'ok', 'Imported recent progress item from Trakt cache')

		message = 'movies=%s episodes=%s progress=%s recent=%s' % (movies, episodes, progress, recent)
		record_provider_sync('trakt', 'local_import', 'success', message, {'movies': movies, 'episodes': episodes, 'progress': progress, 'recent': recent})
		logger('###FenSkeleton WatchState Trakt Import###:', message)
		if not silent: kodi_utils.notification('Trakt synced locally: %s movies / %s episodes' % (movies, episodes), 4000)
		return {'movies': movies, 'episodes': episodes, 'progress': progress, 'recent': recent}
	except Exception as e:
		logger('FenSkeleton WatchState Trakt import failed', str(e))
		record_provider_sync('trakt', 'local_import', 'failed', str(e))
		if not silent: kodi_utils.notification('Watch State Import Failed', 4000)
		return {'movies': 0, 'episodes': 0, 'progress': 0, 'recent': 0, 'error': str(e)}



def _get_sync_completed(provider, sync_type):
	try:
		initialize(silent=True)
		dbcon = connect_watchstate()
		row = dbcon.execute('SELECT last_completed_at FROM provider_sync_state WHERE provider=? AND sync_type=?', (provider, sync_type)).fetchone()
		dbcon.close()
		return row[0] if row else ''
	except Exception:
		return ''


def _trakt_cache_counts():
	counts = {'movies': 0, 'episodes': 0, 'progress': 0}
	try:
		trakt_db = connect_database('trakt_db')
		counts['movies'] = trakt_db.execute("SELECT COUNT(*) FROM watched WHERE db_type='movie'").fetchone()[0]
		counts['episodes'] = trakt_db.execute("SELECT COUNT(*) FROM watched WHERE db_type='episode'").fetchone()[0]
		counts['progress'] = trakt_db.execute("SELECT COUNT(*) FROM progress").fetchone()[0]
		trakt_db.close()
	except Exception as e:
		logger('FenSkeleton WatchState Trakt cache count failed', str(e))
	return counts



def _kodi_busy_for_watchstate():
	"""True when background sync should not run because playback/scraping has priority."""
	try:
		if kodi_utils.get_property('fenskeleton.source_scrape_running') == 'true': return True
	except Exception:
		pass
	try:
		import xbmc
		if xbmc.Player().isPlayingVideo(): return True
	except Exception:
		pass
	return False


def _wait_for_watchstate_idle(initial_delay=180, retry_delay=30, max_wait=900):
	"""Delay local maintenance until Kodi is idle. Return False if it should skip."""
	try: initial_delay = int(initial_delay or 180)
	except Exception: initial_delay = 180
	try: retry_delay = int(retry_delay or 30)
	except Exception: retry_delay = 30
	try: max_wait = int(max_wait or 900)
	except Exception: max_wait = 900
	elapsed = 0
	if initial_delay > 0:
		kodi_utils.sleep(initial_delay * 1000)
		elapsed += initial_delay
	while _kodi_busy_for_watchstate():
		if elapsed >= max_wait:
			logger('###FenSkeleton WatchState Auto Sync###:', 'skipped busy max_wait=%s' % max_wait)
			return False
		kodi_utils.sleep(retry_delay * 1000)
		elapsed += retry_delay
	return True


def auto_import_trakt_cache(reason='auto', min_interval=21600, notify=True, delay=None, max_wait=900):
	"""Background local sync from current Trakt cache. Local-only and Android-safe."""
	try:
		try:
			from modules import settings
			if not settings.trakt_user_active(): return 'no trakt account'
			if delay is None:
				try: delay = int(settings.get_setting('fenskeleton.watchstate.auto_sync_delay', '180'))
				except Exception: delay = 180
			try: min_interval = int(settings.get_setting('fenskeleton.watchstate.auto_sync_interval', str(min_interval)))
			except Exception: pass
			try:
				notify = settings.get_setting('fenskeleton.watchstate.sync_notification', 'true') == 'true'
			except Exception:
				pass
		except Exception:
			pass

		if kodi_utils.get_property('fenskeleton.watchstate_auto_sync_running') == 'true': return 'running'
		current_time = int(time.time())
		last_completed = _get_sync_completed('trakt', 'auto_local_import')
		last_dt = _parse_date(last_completed)
		if last_dt and not int(min_interval or 0) == 0:
			try: last_time = int(time.mktime(last_dt.timetuple()))
			except Exception: last_time = 0
			if last_time and current_time - last_time < int(min_interval):
				return 'throttled'

		# Startup maintenance must never compete with source scraping or playback.
		if not _wait_for_watchstate_idle(initial_delay=delay, retry_delay=30, max_wait=max_wait):
			record_provider_sync('trakt', 'auto_local_import', 'skipped', 'busy playback/scraping', {'reason': reason})
			return 'busy'

		counts = _trakt_cache_counts()
		if counts['movies'] == 0 and counts['episodes'] == 0 and counts['progress'] == 0:
			record_provider_sync('trakt', 'auto_local_import', 'skipped', 'empty trakt cache', counts)
			return 'empty trakt cache'
		if _kodi_busy_for_watchstate():
			record_provider_sync('trakt', 'auto_local_import', 'skipped', 'busy playback/scraping', counts)
			return 'busy'

		kodi_utils.set_property('fenskeleton.watchstate_auto_sync_running', 'true')
		result = import_trakt_cache_to_local(silent=True)
		message = 'movies=%s episodes=%s progress=%s recent=%s reason=%s' % (result.get('movies', 0), result.get('episodes', 0), result.get('progress', 0), result.get('recent', 0), reason)
		record_provider_sync('trakt', 'auto_local_import', 'success', message, result)
		logger('###FenSkeleton WatchState Auto Sync###:', message)
		if notify and (result.get('movies', 0) or result.get('episodes', 0) or result.get('progress', 0)):
			kodi_utils.notification('Trakt synced locally: %s movies / %s episodes' % (result.get('movies', 0), result.get('episodes', 0)), 4000)
		return 'success'
	except Exception as e:
		try: logger('FenSkeleton WatchState auto import failed', str(e))
		except Exception: pass
		record_provider_sync('trakt', 'auto_local_import', 'failed', str(e))
		return 'failed'
	finally:
		try: kodi_utils.clear_property('fenskeleton.watchstate_auto_sync_running')
		except Exception: pass


def record_provider_sync(provider, sync_type, status, message='', extra=None):
	try:
		initialize(silent=True)
		now = utc_now()
		dbcon = connect_watchstate()
		dbcon.execute('''INSERT OR REPLACE INTO provider_sync_state
			(provider, sync_type, last_started_at, last_completed_at, status, message, extra)
			VALUES (?, ?, COALESCE((SELECT last_started_at FROM provider_sync_state WHERE provider=? AND sync_type=?), ?), ?, ?, ?, ?)''',
			(provider, sync_type, provider, sync_type, now, now, status, message, json.dumps(extra or {})))
		dbcon.close()
		return True
	except Exception as e:
		logger('FenSkeleton WatchState sync state failed', str(e))
		return False


def summary(params=None):
	try:
		initialize(silent=True)
		dbcon = connect_watchstate()
		movie_watched = dbcon.execute("SELECT COUNT(*) FROM watch_state WHERE media_type='movie' AND watched=1").fetchone()[0]
		episode_watched = dbcon.execute("SELECT COUNT(*) FROM watch_state WHERE media_type='episode' AND watched=1").fetchone()[0]
		progress_items = dbcon.execute('SELECT COUNT(*) FROM watch_state WHERE progress_percent IS NOT NULL').fetchone()[0]
		recent_items = dbcon.execute('SELECT COUNT(*) FROM recent_activity').fetchone()[0]
		sync_rows = dbcon.execute('SELECT provider, sync_type, status, message, last_completed_at FROM provider_sync_state ORDER BY last_completed_at DESC').fetchall()
		dbcon.close()
		lines = []
		lines.append('[B]FenSkeleton Watch State[/B]')
		lines.append('')
		lines.append('Watched movies: %s' % movie_watched)
		lines.append('Watched episodes: %s' % episode_watched)
		lines.append('Progress items: %s' % progress_items)
		lines.append('Recent activity items: %s' % recent_items)
		if sync_rows:
			lines.append('')
			lines.append('[B]Last sync activity[/B]')
			for provider, sync_type, status, message, completed in sync_rows[:8]:
				lines.append('%s / %s / %s / %s / %s' % (provider, sync_type, status, completed, message))
		return kodi_utils.show_text('Watch State Summary', text='[CR]'.join(lines), font_size='large')
	except Exception as e:
		logger('FenSkeleton WatchState summary failed', str(e))
		return kodi_utils.notification('Watch State Summary Failed', 3000)


def initialize_action(params=None):
	return initialize(silent=False)


def import_trakt_action(params=None):
	return import_trakt_cache_to_local(params=params, silent=False)


def cleanup_action(params=None):
	return cleanup_recent_activity(days=RECENT_DAYS_DEFAULT, silent=False)
