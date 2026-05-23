# -*- coding: utf-8 -*-
import time
from threading import Thread
from urllib.parse import urlencode
from caches.settings_cache import get_setting, set_setting
from caches.main_cache import cache_object
from modules.source_utils import supported_video_extensions, seas_ep_filter, extras
from modules.utils import copy2clip, make_qrcode, make_tinyurl
from modules.kodi_utils import make_session, kodi_dialog, ok_dialog, notification, confirm_dialog, progress_dialog, sleep
# from modules.kodi_utils import logger

session = make_session('https://api.torbox.app/v1/api/')

class TorBoxAPI:
	def __init__(self):
		self.token = get_setting('fenskeleton.tb.token')

	def _get(self, url, data={}):
		if self.token in ('empty_setting', ''): return None
		headers = {'Authorization': 'Bearer %s' % self.token}
		url = 'https://api.torbox.app/v1/api/' + url
		response = session.get(url, params=data, headers=headers, timeout=20)
		return response.json()

	def _post(self, url, params=None, json=None, data=None):
		if self.token in ('empty_setting', '') and not 'token' in url: return None
		headers = {'Authorization': 'Bearer %s' % self.token}
		url = 'https://api.torbox.app/v1/api/' + url
		response = session.post(url, params=params, json=json, data=data, headers=headers, timeout=20)
		return response.json()

	def add_headers_to_url(self, url):
		return url + '|' + urlencode({'User-Agent': 'Mozilla/5.0'})

	def account_info(self):
		return self._get('user/me')

	def user_cloud(self):
		string = 'tb_user_cloud'
		url = 'torrents/mylist'
		return cache_object(self._get, string, url, False, 0.03)

	def user_cloud_usenet(self):
		string = 'tb_user_cloud_usenet'
		url = 'usenet/mylist'
		return cache_object(self._get, string, url, False, 0.03)

	def user_cloud_info(self, request_id=''):
		string = 'tb_user_cloud_%s' % request_id
		url = 'torrents/mylist?id=%s' % request_id
		return cache_object(self._get, string, url, False, 0.03)

	def user_cloud_info_usenet(self, request_id=''):
		string = 'tb_user_cloud_usenet_%s' % request_id
		url = 'usenet/mylist?id=%s' % request_id
		return cache_object(self._get, string, url, False, 0.03)

	def user_cloud_clear(self):
		if not confirm_dialog(): return
		data = {'all': True, 'operation': 'delete'}
		self._post('torrents/controltorrent', json=data)
		self._post('usenet/controlusenetdownload', json=data)
		self.clear_cache()

	def torrent_info(self, request_id=''):
		url = 'torrents/mylist?id=%s' % request_id
		return self._get(url)

	def delete_torrent(self, request_id=''):
		data = {'torrent_id': request_id, 'operation': 'delete'}
		return self._post('torrents/controltorrent', json=data)

	def delete_usenet(self, request_id=''):
		data = {'usenet_id': request_id, 'operation': 'delete'}
		return self._post('usenet/controlusenetdownload', json=data)

	def unrestrict_link(self, file_id):
		torrent_id, file_id = file_id.split(',')
		data = {'token': self.token, 'torrent_id': torrent_id, 'file_id': file_id}
		try: return self._get('torrents/requestdl', data=data)['data']
		except: return None

	def unrestrict_usenet(self, file_id):
		usenet_id, file_id = file_id.split(',')
		params = {'token': self.token, 'usenet_id': usenet_id, 'file_id': file_id, 'user_ip': True}
		try: return self._get('usenet/requestdl', params=params)['data']
		except: return None

	def add_magnet(self, magnet):
		data = {'magnet': magnet, 'seed': 3, 'allow_zip': False}
		return self._post('torrents/createtorrent', data=data)

	def check_cache_single(self, _hash):
		return self._get('torrents/checkcached', data={'hash': _hash, 'format': 'list'})

	def check_cache(self, hashlist):
		data = {'hashes': hashlist}
		return self._post('torrents/checkcached', params={'format': 'list'}, json=data)

	def create_transfer(self, magnet_url):
		result = self.add_magnet(magnet_url)
		if not result['success']: return ''
		return result['data'].get('torrent_id', '')

	def resolve_magnet(self, magnet_url, info_hash, store_to_cloud, title, season, episode):
		try:
			file_url, match, torrent_id = None, False, None
			extensions = supported_video_extensions()
			extras_filter = extras()
			extras_filtering_list = tuple(i for i in extras_filter if not i in title.lower())
			torrent = self.add_magnet(magnet_url)
			if not torrent['success']: return None
			torrent_id = torrent['data']['torrent_id']
			torrent_files = self.torrent_info(torrent_id)
			files = torrent_files['data']['files']
			selected_files = [{'url': '%d,%d' % (torrent_id, item['id']), 'filename': item['short_name'], 'size': item['size']} \
							for item in files if item['short_name'].lower().endswith(tuple(extensions))]
			if not selected_files: return None
			if season:
				selected_files = [i for i in selected_files if seas_ep_filter(season, episode, i['filename'])]
			else:
				if self._m2ts_check(selected_files): return None
				selected_files = [i for i in selected_files if not any(x in i['filename'] for x in extras_filtering_list)]
				selected_files.sort(key=lambda k: k['size'], reverse=True)
			if not selected_files: return None
			file_key = selected_files[0]['url']
			file_url = self.unrestrict_link(file_key)
			if not store_to_cloud: Thread(target=self.delete_torrent, args=(torrent_id,)).start()
			return file_url
		except:
			if torrent_id: self.delete_torrent(torrent_id)
			return None

	def display_magnet_pack(self, magnet_url, info_hash):
		from modules.source_utils import supported_video_extensions
		try:
			torrent_id = None
			extensions = supported_video_extensions()
			torrent = self.add_magnet(magnet_url)
			if not torrent['success']: return None
			torrent_id = torrent['data']['torrent_id']
			torrent_files = self.torrent_info(torrent_id)
			files = torrent_files['data']['files']
			torrent_files = [{'link': '%d,%d' % (torrent_id, item['id']), 'filename': item['short_name'], 'size': item['size']} \
							for item in files if item['short_name'].lower().endswith(tuple(extensions))]
			Thread(target=self.delete_torrent, args=(torrent_id,)).start()
			return torrent_files or None
		except Exception:
			if torrent_id: self.delete_torrent(torrent_id)
			return None

	def _m2ts_check(self, folder_items):
		for item in folder_items:
			if item['filename'].endswith('.m2ts'): return True
		return False

	def auth(self):
		# TorBox device-code authorization. This keeps the saved token in the same
		# fenskeleton.tb.token setting used by the resolver, so no scrape/resolve
		# code has to change. Manual API-key entry remains as a fallback.
		if self.device_auth(): return True
		return self.auth_api_key()

	def device_auth(self):
		self.token = ''
		start_url = 'https://api.torbox.app/v1/api/user/auth/device/start'
		token_url = 'https://api.torbox.app/v1/api/user/auth/device/token'
		try:
			response = session.get(start_url, params={'app': 'FenSkeleton'}, timeout=20).json()
			if not response.get('success'): return False
			data = response.get('data') or {}
			device_code = data.get('device_code')
			user_code = data.get('code')
			auth_url = data.get('verification_url') or 'https://torbox.app/oauth/device'
			friendly_url = data.get('friendly_verification_url') or ''
			if not device_code or not user_code: return False
		except Exception:
			return False

		qr_code = make_qrcode(auth_url) or ''
		short_url = friendly_url or make_tinyurl(auth_url)
		try: copy2clip(auth_url)
		except: pass
		if short_url:
			p_dialog_insert = 'OR visit this URL: [B]%s[/B][CR]OR Enter this Code: [B]%s[/B]' % (short_url, user_code)
		else:
			p_dialog_insert = 'OR visit: [B]https://torbox.app/oauth/device[/B][CR]Enter this Code: [B]%s[/B]' % user_code
		content = 'Please Scan the QR Code[CR]%s[CR]Code expires in about 10 minutes.' % p_dialog_insert
		progressDialog = progress_dialog('TorBox Authorize', qr_code)
		progressDialog.update(content, 0)
		sleep_interval = int(data.get('interval') or 5)
		expires_in = 600
		start, time_passed = time.time(), 0
		while not progressDialog.iscanceled() and time_passed < expires_in and not self.token:
			sleep(1000 * sleep_interval)
			try:
				response = session.post(token_url, json={'device_code': device_code}, timeout=20).json()
			except Exception:
				time_passed = time.time() - start
				progressDialog.update(content, int(100 * time_passed/float(expires_in)))
				continue
			if not response.get('success'):
				error = str(response.get('error') or response.get('detail') or '').lower()
				if 'slow' in error: sleep_interval = max(sleep_interval + 2, 7)
				time_passed = time.time() - start
				progressDialog.update(content, int(100 * time_passed/float(expires_in)))
				continue
			data = response.get('data') or {}
			token = data.get('token') or data.get('api_token') or data.get('apikey') or data.get('access_token') or response.get('token')
			if not token:
				time_passed = time.time() - start
				progressDialog.update(content, int(100 * time_passed/float(expires_in)))
				continue
			self.token = token
			set_setting('tb.token', token)
			set_setting('tb.enabled', 'true')
			break
		try: progressDialog.close()
		except: pass
		if self.token:
			ok_dialog(text='Success')
			return True
		return False

	def auth_api_key(self):
		api_key = kodi_dialog().input('TorBox API Key:')
		if not api_key: return False
		try:
			self.token = api_key
			r = self.account_info()
			if not r.get('success'): raise Exception()
			set_setting('tb.token', api_key)
			set_setting('tb.enabled', 'true')
			message = 'Success'
			status = True
		except:
			message = 'An Error Occurred'
			status = False
		ok_dialog(text=message)
		return status

	def revoke(self):
		if not confirm_dialog(): return
		set_setting('tb.token', 'empty_setting')
		set_setting('tb.enabled', 'false')
		notification('TorBox Authorization Reset', 3000)

	def clear_cache(self, clear_hashes=True):
		try:
			from caches.debrid_cache import debrid_cache
			from caches.base_cache import connect_database
			dbcon = connect_database('maincache_db')
			# USER CLOUD
			try:
				dbcon.execute("""DELETE FROM maincache WHERE id=?""", ('tb_user_cloud',))
				dbcon.execute("""DELETE FROM maincache WHERE id LIKE ?""", ('tb_user_cloud%',))
				user_cloud_success = True
			except: user_cloud_success = False
			# HASH CACHED STATUS
			if clear_hashes:
				try:
					debrid_cache.clear_debrid_results('tb')
					hash_cache_status_success = True
				except: hash_cache_status_success = False
			else: hash_cache_status_success = True
		except: return False
		if False in (user_cloud_success, hash_cache_status_success): return False
		return True

TorBox = TorBoxAPI()

