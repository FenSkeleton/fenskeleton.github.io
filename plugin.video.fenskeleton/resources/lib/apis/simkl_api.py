# -*- coding: utf-8 -*-
"""
FenSkeleton Simkl API integration

v0.0.22 scope:
- PIN/device authorization.
- Provider mode selection.
- New watched/unwatched writes to Simkl.
- Playback progress writes to Simkl via scrobble pause.
- Manual Trakt cache -> Simkl history import with preview + confirmation.
- No automatic mass migration after auth.
"""
from __future__ import absolute_import

import time
import json
import requests
from collections import defaultdict

from caches.settings_cache import get_setting, set_setting
from caches.base_cache import connect_database
from modules import kodi_utils, settings
from modules.utils import copy2clip, make_qrcode, make_tinyurl

logger = kodi_utils.logger

API_ENDPOINT = 'https://api.simkl.com/%s'
PIN_URL = 'https://simkl.com/pin'
APP_NAME = 'fenskeleton'
APP_VERSION = '0.0.24'
_LAST_API_ERROR = {}

def _abort_requested():
	try:
		import xbmc
		return xbmc.Monitor().abortRequested()
	except Exception:
		return False


def _client_id():
	return settings.simkl_client()


def _token():
	return settings.simkl_token()


def _mode():
	try: return int(get_setting('fenskeleton.simkl.provider_mode', '1'))
	except Exception: return 1


def simkl_enabled():
	return _mode() != 0 and _token() not in (None, '', 'empty_setting') and _client_id() not in (None, '', 'empty_setting')


def no_client_key():
	kodi_utils.notification('Simkl Client ID missing', 4000)
	return None


def _base_params(params=None):
	client_id = _client_id()
	if client_id in (None, '', 'empty_setting'):
		return None
	base = {'client_id': client_id, 'app-name': APP_NAME, 'app-version': APP_VERSION}
	if params: base.update(params)
	return base


def _headers(with_auth=False):
	headers = {
		'Content-Type': 'application/json',
		'User-Agent': 'FenSkeleton/%s' % APP_VERSION
	}
	client_id = _client_id()
	if client_id not in (None, '', 'empty_setting'):
		headers['simkl-api-key'] = client_id
	if with_auth:
		token = _token()
		if token not in (None, '', 'empty_setting'):
			headers['Authorization'] = 'Bearer %s' % token
	return headers


def call_simkl(path, params=None, data=None, with_auth=False, method='get', timeout=12):
	global _LAST_API_ERROR
	_LAST_API_ERROR = {}
	try:
		if _abort_requested(): return None
		all_params = _base_params(params or {})
		if all_params is None: return no_client_key()
		url = API_ENDPOINT % path.lstrip('/')
		headers = _headers(with_auth=with_auth)
		method = (method or 'get').lower()
		if _abort_requested(): return None
		if method == 'post':
			response = requests.post(url, params=all_params, json=data or {}, headers=headers, timeout=timeout)
		elif method == 'delete':
			response = requests.delete(url, params=all_params, headers=headers, timeout=timeout)
		else:
			response = requests.get(url, params=all_params, headers=headers, timeout=timeout)
		status = response.status_code
		try: body = response.json()
		except Exception:
			try: body = {'text': response.text[:500]}
			except Exception: body = {}
		if status in (200, 201):
			return body
		# duplicate/recent scrobble conflicts are non-fatal for us
		if status == 409:
			logger('FenSkeleton Simkl API conflict', 'path=%s body=%s' % (path, body))
			return {'conflict': True, 'body': body}
		# Playback state can disappear remotely between callbacks. This is benign.
		if status == 404 and path.lstrip('/').startswith('scrobble/'):
			return {'not_found': True}
		logger('FenSkeleton Simkl API error', 'path=%s status=%s body=%s' % (path, status, body))
		_LAST_API_ERROR = {'path': path, 'status': status, 'body': body}
		return None
	except Exception as e:
		logger('FenSkeleton Simkl API exception', str(e))
		_LAST_API_ERROR = {'path': path, 'status': 0, 'error': str(e)}
		return None


def simkl_get_pin():
	client_id = _client_id()
	if client_id in (None, '', 'empty_setting'): return no_client_key()
	result = call_simkl('oauth/pin', params={'client_id': client_id}, with_auth=False, method='get', timeout=20)
	try: logger('FenSkeleton Simkl PIN result', 'ok' if result and (result.get('user_code') or result.get('code')) else str(result))
	except Exception: pass
	return result


def _pin_code(pin_data):
	if not pin_data: return ''
	return str(pin_data.get('user_code') or pin_data.get('code') or pin_data.get('pin') or '')


def _verification_url(pin_data, code):
	url = ''
	if pin_data:
		url = str(pin_data.get('verification_url') or pin_data.get('verification_uri') or pin_data.get('url') or '')
	if not url: url = PIN_URL
	return url


def simkl_get_pin_token(pin_data):
	if not pin_data:
		logger('FenSkeleton Simkl auth stopped', 'no pin returned')
		return None
	code = _pin_code(pin_data)
	if not code:
		logger('FenSkeleton Simkl auth stopped', 'no code in pin response')
		kodi_utils.notification('Simkl Error: No PIN Code', 4000)
		return None
	client_id = _client_id()
	if client_id in (None, '', 'empty_setting'): return no_client_key()
	result = None
	progressDialog = None
	try:
		expires_in = int(pin_data.get('expires_in') or pin_data.get('expires') or 600)
		interval = max(5, int(pin_data.get('interval') or 5))
		start = time.time()
		verify_url = _verification_url(pin_data, code)
		display_url = verify_url
		if '?' not in display_url and display_url.rstrip('/').endswith('/pin'):
			display_url = '%s/%s' % (display_url.rstrip('/'), code)
		qr_code = make_qrcode(display_url) or ''
		short_url = make_tinyurl(display_url)
		copy2clip(display_url)
		p_dialog_insert = '[CR]OR....[CR]visit [B]%s[/B]' % short_url if short_url else ''
		content = 'Enter [B]%s[/B] at [B]%s[/B][CR]OR....[CR]Scan the [B]QR Code[/B]%s[CR][CR]Checking every %s seconds.' % (code, verify_url, p_dialog_insert, interval)
		progressDialog = kodi_utils.progress_dialog('Simkl Authorize', qr_code)
		progressDialog.update(content, 0)
		poll_no = 0
		while not progressDialog.iscanceled():
			if time.time() - start >= expires_in:
				logger('FenSkeleton Simkl PIN timeout', 'no token after %s seconds' % int(time.time() - start))
				break
			kodi_utils.sleep(interval * 1000)
			poll_no += 1
			try:
				params = _base_params({'client_id': client_id}) or {'client_id': client_id}
				response = requests.get(API_ENDPOINT % ('oauth/pin/%s' % code), params=params, headers=_headers(False), timeout=20)
				status_code = response.status_code
				try: body = response.json()
				except Exception:
					try: body = {'text': response.text[:500]}
					except Exception: body = {}
				safe_body = '[redacted token response]' if status_code in (200, 201) and ('access_token' in body or 'token' in body) else str(body)[:500]
				logger('FenSkeleton Simkl token poll %s' % poll_no, 'status=%s body=%s' % (status_code, safe_body))
				if status_code in (200, 201):
					token = body.get('access_token') or body.get('token')
					if token:
						result = body
						break
				elif status_code in (400, 404):
					progress = min(99, int(100 * (time.time() - start) / float(expires_in)))
					progressDialog.update(content, progress)
					continue
				elif status_code == 429:
					interval += 5
					progressDialog.update(content + '[CR]Slowing down polling...', min(99, int(100 * (time.time() - start) / float(expires_in))))
					continue
				else:
					break
			except Exception as e:
				logger('FenSkeleton Simkl token poll exception', str(e))
				break
	except Exception as e:
		logger('FenSkeleton Simkl device token fatal', str(e))
	try:
		if progressDialog: progressDialog.close()
	except Exception: pass
	return result


def simkl_authenticate(dummy=''):
	logger('FenSkeleton Simkl authenticate', 'started')
	pin = simkl_get_pin()
	token = simkl_get_pin_token(pin)
	if token:
		access_token = token.get('access_token') or token.get('token')
		if access_token:
			set_setting('simkl.token', access_token)
			set_setting('simkl.user', 'Authorized')
			try:
				user_id = token.get('user_id') or token.get('account_id') or token.get('uid')
				if user_id: set_setting('simkl.user', str(user_id))
			except Exception: pass
			if get_setting('fenskeleton.simkl.provider_mode', 'empty_setting') in ('empty_setting', '', None, '0'):
				set_setting('simkl.provider_mode', '1')
			if _mode() == 1: set_setting('watched_indicators', '2')
			kodi_utils.notification('Simkl Account Authorized', 3000)
			logger('FenSkeleton Simkl token', 'received')
			try:
				import xbmcgui
				if xbmcgui.Dialog().yesno('Build Simkl Watch State', 'Download your Simkl watched history, progress and Next Episodes now?'):
					simkl_sync(force=True, silent=False)
			except Exception as e:
				logger('FenSkeleton Simkl initial sync prompt failed', str(e))
			return True
	logger('FenSkeleton Simkl authenticate', 'no token returned')
	kodi_utils.notification('Simkl Error Authorizing', 3000)
	return False


def simkl_revoke_authentication(dummy=''):
	try:
		set_setting('simkl.token', 'empty_setting')
		set_setting('simkl.user', 'empty_setting')
		kodi_utils.notification('Simkl Authorization Cleared', 3000)
		logger('FenSkeleton Simkl revoke', 'local token cleared')
		return True
	except Exception as e:
		logger('FenSkeleton Simkl revoke failed', str(e))
		kodi_utils.notification('Simkl Revoke Failed', 3000)
		return False


def simkl_status(dummy=''):
	token = _token()
	client_id = _client_id()
	if client_id in (None, '', 'empty_setting'): return no_client_key()
	if token in (None, '', 'empty_setting'):
		kodi_utils.notification('Simkl Not Authorized', 3500)
		logger('FenSkeleton Simkl status', 'not authorized')
		return False
	result = call_simkl('users/settings', with_auth=True, method='get', timeout=15)
	errors = [dict(_LAST_API_ERROR)] if not result else []
	if not result:
		result = call_simkl('users/settings', with_auth=True, method='post', timeout=15)
		if not result: errors.append(dict(_LAST_API_ERROR))
	if result:
		try:
			username = result.get('user', {}).get('name') or result.get('user', {}).get('login') or result.get('account', {}).get('name')
			if username: set_setting('simkl.user', str(username))
		except Exception: pass
		kodi_utils.notification('Simkl Authorized', 3000)
		logger('FenSkeleton Simkl status', 'authorized')
		return True
	invalid_token = any(error.get('status') in (401, 403) for error in errors)
	if invalid_token:
		kodi_utils.notification('Simkl Authorization Invalid', 4000)
		logger('FenSkeleton Simkl status', 'authorization rejected')
	else:
		kodi_utils.notification('Unable to Reach Simkl', 4000)
		logger('FenSkeleton Simkl status', 'API status check failed')
	return False


def simkl_set_mode(dummy=''):
	try:
		import xbmcgui
		options = ['Off', 'Simkl Only', 'Trakt + Simkl']
		current = _mode()
		choice = xbmcgui.Dialog().select('Simkl Watch State Mode', options, preselect=current)
		if choice < 0: return False
		set_setting('simkl.provider_mode', str(choice))
		# Simkl Only must read indicators and resume points from the native
		# Simkl cache. Combined mode keeps Trakt as the stable read authority.
		if choice == 1: set_setting('watched_indicators', '2')
		elif choice == 2 and settings.trakt_user_active(): set_setting('watched_indicators', '1')
		elif choice == 0 and int(get_setting('fenskeleton.watched_indicators', '0')) == 2: set_setting('watched_indicators', '0')
		kodi_utils.notification('Simkl Mode: %s' % options[choice], 3000)
		logger('FenSkeleton Simkl mode', options[choice])
		return True
	except Exception as e:
		logger('FenSkeleton Simkl mode failed', str(e))
		return False


def _utc_now():
	return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _simkl_data_get(key, default=None):
	try:
		dbcon = connect_database('simkl_db')
		row = dbcon.execute('SELECT data FROM simkl_data WHERE id=?', (key,)).fetchone()
		dbcon.close()
		return json.loads(row[0]) if row else default
	except Exception:
		return default


def _simkl_data_set(key, value):
	try:
		dbcon = connect_database('simkl_db')
		dbcon.execute('INSERT OR REPLACE INTO simkl_data VALUES (?, ?)', (key, json.dumps(value)))
		dbcon.close()
		return True
	except Exception as e:
		logger('FenSkeleton Simkl cache metadata failed', str(e))
		return False


def _media_object(item, category):
	if category == 'movies': return item.get('movie') or item
	return item.get('show') or item.get('anime') or item


def _tmdb_id(media):
	ids = (media or {}).get('ids') or {}
	value = ids.get('tmdb') or ids.get('tmdb_id')
	try: return str(int(value))
	except Exception: return ''


def _normalise_all_items(result):
	"""Turn /sync/all-items into FenSkeleton's watched-cache contract."""
	watched, statuses, next_items = [], [], []
	if not isinstance(result, dict): return watched, statuses, next_items
	for category in ('movies', 'shows', 'anime'):
		for item in result.get(category, []) or []:
			media = _media_object(item, category)
			media_id = _tmdb_id(media)
			if not media_id: continue
			title = media.get('title') or item.get('title') or ''
			status = item.get('status') or ''
			statuses.append((category, media_id, status))
			last_watched = item.get('last_watched_at') or item.get('last_watched') or item.get('watched_at') or ''
			if category == 'movies':
				if status == 'completed' or item.get('watched_at') or item.get('last_watched_at'):
					watched.append(('movie', media_id, 0, 0, last_watched, title))
			else:
				for season in item.get('seasons', []) or []:
					season_num = season.get('number', season.get('season', 0))
					for episode in season.get('episodes', []) or []:
						episode_num = episode.get('number', episode.get('episode', 0))
						episode_watched = episode.get('watched_at') or episode.get('last_watched_at') or last_watched
						if episode.get('watched', True) is not False:
							watched.append(('episode', media_id, int(season_num or 0), int(episode_num or 0), episode_watched, title))
			next_info = item.get('next_to_watch_info') or {}
			if next_info:
				next_items.append({'media_ids': {'tmdb': int(media_id)}, 'season': int(next_info.get('season') or 1),
					'episode': max(0, int(next_info.get('episode') or 1) - 1), 'title': title,
					'last_played': last_watched or '2000-01-01T00:00:00.000Z'})
	return watched, statuses, next_items


def _normalise_playback(result):
	rows = []
	for item in result or []:
		media = item.get('movie') or item.get('show') or item.get('anime') or {}
		media_id = _tmdb_id(media)
		if not media_id: continue
		episode = item.get('episode') or {}
		if not isinstance(episode, dict): episode = {'number': episode}
		is_episode = bool(episode) or item.get('season') is not None
		season_num = episode.get('season') or item.get('season') or 0
		episode_num = episode.get('number') or episode.get('episode') or item.get('episode_number') or 0
		progress = item.get('progress') or 0
		position = item.get('current_position') or 0
		resume_id = item.get('id') or item.get('playback_id') or 0
		title = media.get('title') or ''
		updated = item.get('paused_at') or item.get('updated_at') or _utc_now()
		rows.append(('episode' if is_episode else 'movie', media_id, int(season_num), int(episode_num), str(progress), str(position), updated, resume_id, title))
	return rows


def _fetch_simkl_library(date_from=None, progress=None):
	params = {'extended': 'full', 'episode_watched_at': 'yes', 'include_all_episodes': 'yes', 'next_watch_info': 'yes'}
	if date_from: params['date_from'] = date_from
	if date_from:
		result = call_simkl('sync/all-items', params=params, with_auth=True, timeout=90)
		return result if isinstance(result, dict) else None
	combined = {'movies': [], 'shows': [], 'anime': []}
	# Simkl explicitly asks media-centre clients to perform initial full pulls sequentially.
	for count, category in enumerate(('shows', 'movies', 'anime'), 1):
		if progress: progress.update((count - 1) * 25, '[B]Downloading Simkl Watch State[/B]', category.title())
		result = call_simkl('sync/all-items/%s' % category, params=params, with_auth=True, timeout=120)
		if result is None: return None
		if isinstance(result, dict):
			combined[category] = result.get(category, []) or result.get('items', []) or []
		elif isinstance(result, list): combined[category] = result
	return combined


def simkl_sync(force=False, silent=False):
	"""Native Simkl -> local cache sync. Full once, then activities-gated deltas."""
	if not simkl_enabled():
		if not silent: kodi_utils.notification('Authorize Simkl First', 3500)
		return False
	progress = None
	try:
		activities = call_simkl('sync/activities', with_auth=True, timeout=30)
		if not isinstance(activities, dict): raise Exception('activities unavailable')
		last_sync = _simkl_data_get('last_sync', '')
		activity_stamp = activities.get('all') or ''
		if not force and last_sync and activity_stamp == last_sync:
			if not silent: kodi_utils.notification('Simkl Already Up to Date', 2500)
			return True
		previous_activities = _simkl_data_get('activities', {}) or {}
		removed_changed = any((activities.get(k, {}) or {}).get('removed_from_list') != (previous_activities.get(k, {}) or {}).get('removed_from_list') for k in ('movies', 'tv_shows', 'anime'))
		full = force or not last_sync or removed_changed
		if full and not silent:
			progress = kodi_utils.kodi_progress_background()
			progress.create('[B]Building Simkl Watch State[/B]', 'This one-time download may take a few minutes')
		result = _fetch_simkl_library(None if full else last_sync, progress=progress)
		if result is None: raise Exception('library sync unavailable')
		# Simkl's bootstrap contract requires the watermark to be captured after
		# the sequential full-library pull, not before it began.
		if full:
			activities = call_simkl('sync/activities', with_auth=True, timeout=30)
			if not isinstance(activities, dict): raise Exception('post-bootstrap activities unavailable')
			activity_stamp = activities.get('all') or ''
			if not activity_stamp: raise Exception('post-bootstrap activity watermark unavailable')
		watched, statuses, next_items = _normalise_all_items(result)
		playback = call_simkl('sync/playback', with_auth=True, timeout=45)
		if playback is None: raise Exception('playback sync unavailable')
		if progress: progress.update(85, '[B]Building Simkl Watch State[/B]', 'Resume points and Next Episodes')
		progress_rows = _normalise_playback(playback if isinstance(playback, list) else playback.get('items', []))
		if full: merged_next = next_items
		else:
			touched = set((row[1] for row in statuses))
			merged_next = [i for i in simkl_next_items() if str(i.get('media_ids', {}).get('tmdb')) not in touched]
			merged_next.extend(next_items)
		dbcon = connect_database('simkl_db')
		try:
			dbcon.execute('BEGIN IMMEDIATE')
			if full:
				dbcon.execute('DELETE FROM watched')
				dbcon.execute('DELETE FROM watched_status')
			else:
				# A delta contains the authoritative current state for every touched
				# item. Remove its previous rows first so unwatched episodes and list
				# moves do not linger locally.
				for media_id in touched:
					dbcon.execute('DELETE FROM watched WHERE media_id=?', (media_id,))
					dbcon.execute('DELETE FROM watched_status WHERE media_id=?', (media_id,))
			if watched: dbcon.executemany('INSERT OR REPLACE INTO watched VALUES (?, ?, ?, ?, ?, ?)', watched)
			if statuses: dbcon.executemany('INSERT OR REPLACE INTO watched_status VALUES (?, ?, ?)', statuses)
			dbcon.execute('DELETE FROM progress')
			if progress_rows: dbcon.executemany('INSERT OR REPLACE INTO progress VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', progress_rows)
			for key, value in (('next_items', merged_next), ('activities', activities), ('last_sync', activity_stamp or _utc_now())):
				dbcon.execute('INSERT OR REPLACE INTO simkl_data VALUES (?, ?)', (key, json.dumps(value)))
			dbcon.execute('COMMIT')
		except Exception:
			try: dbcon.execute('ROLLBACK')
			except Exception: pass
			raise
		finally:
			dbcon.close()
		message = 'full=%s watched=%s progress=%s next=%s' % (full, len(watched), len(progress_rows), len(merged_next))
		logger('FenSkeleton Simkl native sync', message)
		if not silent: kodi_utils.notification('Simkl Sync Complete', 3500)
		return True
	except Exception as e:
		logger('FenSkeleton Simkl native sync failed', str(e))
		if not silent: kodi_utils.notification('Simkl Sync Failed', 4000)
		return False
	finally:
		try:
			if progress: progress.close()
		except Exception: pass


def simkl_refresh(dummy=''):
	return simkl_sync(force=False, silent=False)


def simkl_auto_refresh():
	"""Cheap activities-gated refresh; never performs an unapproved first full pull."""
	if not simkl_enabled() or not _simkl_data_get('last_sync', ''): return False
	return simkl_sync(force=False, silent=True)


def simkl_rebuild(dummy=''):
	try:
		import xbmcgui
		if not xbmcgui.Dialog().yesno('Rebuild Simkl Watch State', 'Replace the local Simkl cache with a fresh copy from Simkl?'): return False
	except Exception: pass
	return simkl_sync(force=True, silent=False)


def simkl_next_items():
	return _simkl_data_get('next_items', []) or []


def _simkl_status_items(media_type, status):
	try:
		categories = ('movies',) if media_type in ('movie', 'movies') else ('shows', 'anime')
		dbcon = connect_database('simkl_db')
		rows = dbcon.execute('SELECT media_id FROM watched_status WHERE db_type IN (%s) AND status=?' % ','.join('?' * len(categories)), tuple(categories) + (status,)).fetchall()
		dbcon.close()
		return [{'media_ids': {'tmdb': int(row[0])}} for row in rows]
	except Exception: return []


def simkl_watching(media_type, page_no=1): return _simkl_status_items(media_type, 'watching')
def simkl_plan_to_watch(media_type, page_no=1): return _simkl_status_items(media_type, 'plantowatch')
def simkl_completed(media_type, page_no=1): return _simkl_status_items(media_type, 'completed')
def simkl_on_hold(media_type, page_no=1): return _simkl_status_items(media_type, 'hold')
def simkl_dropped(media_type, page_no=1): return _simkl_status_items(media_type, 'dropped')


def simkl_list_manager(params=None):
	params = params or {}
	if not simkl_enabled(): return kodi_utils.notification('Authorize Simkl First', 3500)
	try:
		import xbmcgui
		media_type = params.get('media_type', 'movie')
		if media_type == 'movie':
			options = [('Plan to Watch', 'plantowatch'), ('Completed', 'completed'), ('Dropped', 'dropped')]
			bucket = 'movies'
		else:
			options = [('Watching', 'watching'), ('Plan to Watch', 'plantowatch'), ('On Hold', 'hold'), ('Completed', 'completed'), ('Dropped', 'dropped')]
			bucket = 'shows'
		choice = xbmcgui.Dialog().select('Move to Simkl List', [i[0] for i in options])
		if choice < 0: return False
		status = options[choice][1]
		item = {'ids': _ids(tmdb_id=params.get('tmdb_id'), imdb_id=params.get('imdb_id'), tvdb_id=params.get('tvdb_id'))}
		if params.get('title'): item['title'] = params.get('title')
		if params.get('year'): item['year'] = params.get('year')
		result = call_simkl('sync/add-to-list', data={'to': status, bucket: [item]}, with_auth=True, method='post', timeout=30)
		if not result: return kodi_utils.notification('Simkl List Update Failed', 3500)
		dbcon = connect_database('simkl_db')
		dbcon.execute('INSERT OR REPLACE INTO watched_status VALUES (?, ?, ?)', (bucket, str(params.get('tmdb_id')), status))
		dbcon.close()
		kodi_utils.notification('Simkl: %s' % options[choice][0], 3000)
		kodi_utils.kodi_refresh()
		return True
	except Exception as e:
		logger('FenSkeleton Simkl list manager failed', str(e))
		return False


def _ids(tmdb_id=None, imdb_id=None, tvdb_id=None):
	ids = {}
	try:
		if imdb_id and imdb_id not in ('None', '0', 'empty_setting'): ids['imdb'] = str(imdb_id)
	except Exception: pass
	try:
		if tmdb_id and str(tmdb_id) not in ('None', '0', 'empty_setting'): ids['tmdb'] = str(tmdb_id)
	except Exception: pass
	try:
		if tvdb_id and str(tvdb_id) not in ('None', '0', 'empty_setting'): ids['tvdb'] = str(tvdb_id)
	except Exception: pass
	return ids


def _movie_item(tmdb_id='', title='', year='', imdb_id='', watched_at=None):
	item = {'ids': _ids(tmdb_id=tmdb_id, imdb_id=imdb_id)}
	if title: item['title'] = title
	try:
		if year: item['year'] = int(year)
	except Exception: pass
	if watched_at: item['watched_at'] = watched_at
	return item


def _episode_payload(tmdb_id='', tvdb_id='', title='', year='', season=None, episode=None, watched_at=None, singular=False):
	show = {'ids': _ids(tmdb_id=tmdb_id, tvdb_id=tvdb_id)}
	if title: show['title'] = title
	try:
		if year: show['year'] = int(year)
	except Exception: pass
	ep = {'number': int(episode)}
	if watched_at: ep['watched_at'] = watched_at
	if singular:
		return {'show': show, 'episode': {'season': int(season), 'number': int(episode)}}
	show['seasons'] = [{'number': int(season), 'episodes': [ep]}]
	return show


def _record_simkl_event(action, media_type, tmdb_id, season='', episode='', title='', status='ok', message='', extra=None):
	try:
		from modules import watchstate
		watchstate.record_activity(action, media_type, tmdb_id, season, episode, title, 'simkl', status, message, extra or {})
	except Exception: pass


def simkl_mark_watched(media_type, tmdb_id, title='', year='', season='', episode='', tvdb_id='', imdb_id='', watched_at=None, remove=False):
	"""Write a watched/unwatched event to Simkl. Non-blocking callers should run this in a thread."""
	if not simkl_enabled(): return False
	try:
		if not watched_at: watched_at = _utc_now()
		if media_type == 'movie':
			payload = {'movies': [_movie_item(tmdb_id, title, year, imdb_id, None if remove else watched_at)]}
		else:
			payload = {'shows': [_episode_payload(tmdb_id, tvdb_id, title, year, season, episode, None if remove else watched_at)]}
		endpoint = 'sync/history/remove' if remove else 'sync/history'
		result = call_simkl(endpoint, data=payload, with_auth=True, method='post', timeout=12)
		ok = bool(result)
		message = 'sent' if ok else 'failed'
		_record_simkl_event('history_remove' if remove else 'history_add', media_type, tmdb_id, season, episode, title, 'ok' if ok else 'failed', message, {'payload': payload, 'response': result or {}})
		logger('FenSkeleton Simkl history %s' % ('remove' if remove else 'add'), '%s %s S%sE%s %s' % (media_type, tmdb_id, season, episode, message))
		return ok
	except Exception as e:
		logger('FenSkeleton Simkl mark watched failed', str(e))
		_record_simkl_event('history_add', media_type, tmdb_id, season, episode, title, 'failed', str(e))
		return False


def simkl_save_progress(media_type, tmdb_id, title='', year='', season='', episode='', tvdb_id='', imdb_id='', progress_percent=0):
	"""Save playback progress to Simkl without marking watched. Uses scrobble/pause."""
	if not simkl_enabled(): return False
	try:
		try: progress_percent = max(0, min(100, float(progress_percent)))
		except Exception: progress_percent = 0
		if media_type == 'movie':
			payload = {'movie': _movie_item(tmdb_id, title, year, imdb_id)}
		else:
			payload = _episode_payload(tmdb_id, tvdb_id, title, year, season, episode, singular=True)
		payload['progress'] = progress_percent
		result = call_simkl('scrobble/pause', data=payload, with_auth=True, method='post', timeout=12)
		ok = bool(result)
		_record_simkl_event('progress_pause', media_type, tmdb_id, season, episode, title, 'ok' if ok else 'failed', 'progress=%s' % progress_percent, {'payload': payload, 'response': result or {}})
		logger('FenSkeleton Simkl progress pause', '%s %s S%sE%s progress=%s ok=%s' % (media_type, tmdb_id, season, episode, progress_percent, ok))
		return ok
	except Exception as e:
		logger('FenSkeleton Simkl progress failed', str(e))
		_record_simkl_event('progress_pause', media_type, tmdb_id, season, episode, title, 'failed', str(e))
		return False


def simkl_scrobble(action, media_type, tmdb_id, title='', year='', season='', episode='', tvdb_id='', imdb_id='', progress_percent=0):
	"""Send a start/pause/stop event using Simkl's native playback lifecycle."""
	if action == 'pause':
		return simkl_save_progress(media_type, tmdb_id, title, year, season, episode, tvdb_id, imdb_id, progress_percent)
	if action not in ('start', 'stop') or not simkl_enabled(): return False
	try:
		if media_type == 'movie': payload = {'movie': _movie_item(tmdb_id, title, year, imdb_id)}
		else: payload = _episode_payload(tmdb_id, tvdb_id, title, year, season, episode, singular=True)
		payload['progress'] = max(0, min(100, float(progress_percent or 0)))
		result = call_simkl('scrobble/%s' % action, data=payload, with_auth=True, method='post', timeout=15)
		ok = bool(result)
		_record_simkl_event('scrobble_%s' % action, media_type, tmdb_id, season, episode, title, 'ok' if ok else 'failed', 'progress=%s' % payload['progress'])
		return ok
	except Exception as e:
		logger('FenSkeleton Simkl scrobble %s failed' % action, str(e))
		return False


def simkl_mark_episode_batch(tmdb_id, title, episodes, tvdb_id='', remove=False):
	"""Batch whole-show/season context-menu changes into one serialized Sync write."""
	if not simkl_enabled() or not episodes: return False
	seasons = defaultdict(list)
	for season, episode, watched_at in episodes:
		item = {'number': int(episode)}
		if watched_at: item['watched_at'] = watched_at
		seasons[int(season)].append(item)
	show = {'title': title or '', 'ids': _ids(tmdb_id=tmdb_id, tvdb_id=tvdb_id),
		'seasons': [{'number': number, 'episodes': values} for number, values in sorted(seasons.items())]}
	endpoint = 'sync/history/remove' if remove else 'sync/history'
	return bool(call_simkl(endpoint, data={'shows': [show]}, with_auth=True, method='post', timeout=60))


def simkl_clear_playback(playback_id):
	if not simkl_enabled() or not playback_id: return False
	return bool(call_simkl('sync/playback/%s' % playback_id, with_auth=True, method='delete', timeout=15))


def _chunk(items, size):
	for i in range(0, len(items), size):
		yield items[i:i+size]


def _trakt_import_data():
	trakt_db = connect_database('trakt_db')
	rows = trakt_db.execute('SELECT db_type, media_id, season, episode, last_played, title FROM watched ORDER BY db_type, media_id, season, episode').fetchall()
	trakt_db.close()
	movies = []
	shows = {}
	for db_type, media_id, season, episode, last_played, title in rows:
		if db_type == 'movie':
			movies.append(_movie_item(media_id, title, '', '', last_played))
		elif db_type == 'episode':
			show = shows.setdefault(str(media_id), {'ids': _ids(tmdb_id=media_id), 'title': title or '', 'seasons_map': defaultdict(list)})
			ep = {'number': int(episode)}
			if last_played: ep['watched_at'] = last_played
			show['seasons_map'][int(season)].append(ep)
	show_items = []
	for k, show in shows.items():
		seasons = []
		for number in sorted(show.pop('seasons_map').keys()):
			seasons.append({'number': int(number), 'episodes': show['seasons_map'][number] if 'seasons_map' in show else []})
		# Above pop removes seasons_map, rebuild correctly from local copy not available? handled below in safer loop.
	return movies, rows


def _trakt_import_payloads():
	trakt_db = connect_database('trakt_db')
	rows = trakt_db.execute('SELECT db_type, media_id, season, episode, last_played, title FROM watched ORDER BY db_type, media_id, season, episode').fetchall()
	trakt_db.close()
	movies = []
	shows_map = {}
	for db_type, media_id, season, episode, last_played, title in rows:
		if db_type == 'movie':
			movies.append(_movie_item(media_id, title, '', '', last_played))
		elif db_type == 'episode':
			key = str(media_id)
			if key not in shows_map: shows_map[key] = {'ids': _ids(tmdb_id=media_id), 'title': title or '', 'seasons': {}}
			season_num = int(season)
			shows_map[key]['seasons'].setdefault(season_num, [])
			ep_item = {'number': int(episode)}
			if last_played: ep_item['watched_at'] = last_played
			shows_map[key]['seasons'][season_num].append(ep_item)
	shows = []
	for key, item in shows_map.items():
		shows.append({'ids': item['ids'], 'title': item.get('title', ''), 'seasons': [{'number': s, 'episodes': eps} for s, eps in sorted(item['seasons'].items())]})
	return movies, shows


def simkl_import_trakt_history(dummy=''):
	"""Manual Trakt -> Simkl import. Never runs automatically."""
	if not simkl_enabled():
		kodi_utils.notification('Authorize Simkl First', 3500)
		return False
	try:
		import xbmcgui
		movies, shows = _trakt_import_payloads()
		episode_count = sum(len(ep_list['episodes']) for show in shows for ep_list in show.get('seasons', []))
		message = 'This will send your current Trakt watched cache to Simkl.[CR][CR]Movies: %s[CR]Episodes: %s[CR][CR]Continue?' % (len(movies), episode_count)
		if not xbmcgui.Dialog().yesno('Import Trakt History to Simkl', message):
			logger('FenSkeleton Simkl Trakt import', 'cancelled')
			return False
		progress = kodi_utils.kodi_progress_background()
		progress.create('[B]Importing Trakt History to Simkl[/B]', '')
		movie_sent = show_sent = failed = 0
		# movies in safe chunks
		for batch in _chunk(movies, 50):
			progress.update(0, '[B]Importing Movies[/B]', '%s / %s' % (movie_sent, len(movies)))
			result = call_simkl('sync/history', data={'movies': batch}, with_auth=True, method='post', timeout=30)
			if result: movie_sent += len(batch)
			else: failed += len(batch)
			kodi_utils.sleep(500)
		# shows in safe chunks
		show_total = len(shows)
		for batch in _chunk(shows, 5):
			percent = min(99, int(float(show_sent) / float(show_total or 1) * 100))
			progress.update(percent, '[B]Importing TV Shows[/B]', '%s / %s shows' % (show_sent, show_total))
			result = call_simkl('sync/history', data={'shows': batch}, with_auth=True, method='post', timeout=45)
			if result: show_sent += len(batch)
			else: failed += len(batch)
			kodi_utils.sleep(750)
		progress.close()
		msg = 'movies=%s shows=%s episodes=%s failed_batches_or_items=%s' % (movie_sent, show_sent, episode_count, failed)
		_record_simkl_event('trakt_import', 'mixed', '', '', '', 'Trakt Import', 'ok' if failed == 0 else 'partial', msg)
		logger('FenSkeleton Simkl Trakt import complete', msg)
		kodi_utils.notification('Simkl import sent: %s movies / %s episodes' % (movie_sent, episode_count), 5000)
		return failed == 0
	except Exception as e:
		logger('FenSkeleton Simkl Trakt import failed', str(e))
		kodi_utils.notification('Simkl Import Failed', 4000)
		return False
