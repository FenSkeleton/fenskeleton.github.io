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
APP_VERSION = '0.0.22'


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


def call_simkl(path, params=None, data=None, with_auth=False, method='get', timeout=20):
	try:
		all_params = _base_params(params or {})
		if all_params is None: return no_client_key()
		url = API_ENDPOINT % path.lstrip('/')
		headers = _headers(with_auth=with_auth)
		method = (method or 'get').lower()
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
		logger('FenSkeleton Simkl API error', 'path=%s status=%s body=%s' % (path, status, body))
		return None
	except Exception as e:
		logger('FenSkeleton Simkl API exception', str(e))
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
			kodi_utils.notification('Simkl Account Authorized', 3000)
			logger('FenSkeleton Simkl token', 'received')
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
	result = call_simkl('users/settings', with_auth=True, method='get', timeout=15) or call_simkl('users/settings', with_auth=True, method='post', timeout=15)
	if result:
		try:
			username = result.get('user', {}).get('name') or result.get('user', {}).get('login') or result.get('account', {}).get('name')
			if username: set_setting('simkl.user', str(username))
		except Exception: pass
		kodi_utils.notification('Simkl Authorized', 3000)
		logger('FenSkeleton Simkl status', 'authorized')
		return True
	kodi_utils.notification('Simkl Token Stored', 3000)
	logger('FenSkeleton Simkl status', 'token stored; status endpoint not confirmed')
	return True


def simkl_set_mode(dummy=''):
	try:
		import xbmcgui
		options = ['Off', 'Simkl Only', 'Trakt + Simkl']
		current = _mode()
		choice = xbmcgui.Dialog().select('Simkl Watch State Mode', options, preselect=current)
		if choice < 0: return False
		set_setting('simkl.provider_mode', str(choice))
		kodi_utils.notification('Simkl Mode: %s' % options[choice], 3000)
		logger('FenSkeleton Simkl mode', options[choice])
		return True
	except Exception as e:
		logger('FenSkeleton Simkl mode failed', str(e))
		return False


def _utc_now():
	return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


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
