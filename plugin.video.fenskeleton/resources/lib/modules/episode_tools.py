# -*- coding: utf-8 -*-
import sys
import json
import random
from datetime import date
from modules.sources import Sources
from modules.settings import date_offset, watched_indicators, ignore_articles, playback_key, max_threads
from modules.metadata import episodes_meta, all_episodes_meta, tvshow_meta
from modules.watched_status import get_watched_status_episode, get_next_episodes, get_hidden_progress_items, watched_info_episode, get_next
from modules.utils import adjust_premiered_date, get_datetime, get_current_timestamp, title_key, TaskPool
from modules import kodi_utils
# logger = kodi_utils.logger

class EpisodeTools:
        def __init__(self, meta, nextep_settings=None):
                self.meta = meta
                self.meta_get = self.meta.get
                self.nextep_settings = nextep_settings

        def next_episode_info(self):
                try:
                        if self.nextep_settings and self.nextep_settings.get('random_next_up'):
                                return self.random_next_up_info(first_run=False)
                        play_type = self.nextep_settings['play_type']
                        season_data = self.meta_get('season_data')
                        watch_count = self.meta_get('watch_count')
                        current_season, current_episode = int(self.meta_get('season')), int(self.meta_get('episode'))
                        watched_info = watched_info_episode(self.meta_get('tmdb_id'))
                        season, episode = get_next(current_season, current_episode, watched_info, season_data, 0)
                        playcount = get_watched_status_episode(watched_info, (season, episode))
                        ep_data = episodes_meta(season, self.meta)
                        if not ep_data: return 'no_next_episode'
                        ep_data = next((i for i in ep_data if i['episode'] == episode), None)
                        if not ep_data: return 'no_next_episode'
                        adjust_hours, current_date = date_offset(), get_datetime()
                        episode_date, premiered = adjust_premiered_date(ep_data['premiered'], adjust_hours)
                        if not episode_date or current_date < episode_date: return 'no_next_episode'
                        custom_title = self.meta_get('custom_title', None)
                        title = custom_title or self.meta_get('title')
                        display_name = '%s - %dx%.2d' % (title, int(season), int(episode))
                        self.meta.update({'media_type': 'episode', 'rootname': display_name, 'season': season, 'ep_name': ep_data['title'], 'ep_thumb': ep_data.get('thumb', None),
                                                        'episode': episode, 'premiered': premiered, 'plot': ep_data['plot']})
                        url_params = {'media_type': 'episode', 'tmdb_id': self.meta_get('tmdb_id'), 'tvshowtitle': self.meta_get('rootname'), 'season': season, 'playcount': playcount,
                                                'episode': episode, 'background': 'true', 'nextep_settings': self.nextep_settings, 'play_type': play_type, 'watch_count': watch_count}
                        if play_type == 'autoscrape_nextep': url_params['prescrape'] = 'false'
                        if custom_title: url_params['custom_title'] = custom_title
                        if 'custom_year' in self.meta: url_params['custom_year'] = self.meta_get('custom_year')
                except: url_params = 'error'
                return self.add_playback_key(url_params)

        def get_random_episode(self, continual=False, first_run=True):
                try:
                        adjust_hours, current_date = date_offset(), get_datetime()
                        tmdb_id = self.meta_get('tmdb_id')
                        tmdb_key = str(tmdb_id)
                        ep_meta = all_episodes_meta(self.meta)
                        episodes_data = [i for i in ep_meta if i['premiered'] and adjust_premiered_date(i['premiered'], adjust_hours)[0] <= current_date]
                        if continual:
                                episode_list = []
                                try:
                                        episode_history = json.loads(kodi_utils.get_property('fenskeleton.random_episode_history'))
                                        if tmdb_key in episode_history: episode_list = episode_history[tmdb_key]
                                        else: kodi_utils.set_property('fenskeleton.random_episode_history', '')
                                except: kodi_utils.set_property('fenskeleton.random_episode_history', '')
                                episodes_data = [i for i in episodes_data if not i in episode_list]
                                if not episodes_data:
                                        kodi_utils.set_property('fenskeleton.random_episode_history', '')
                                        return self.get_random_episode(continual=True)
                        chosen_episode = random.choice(episodes_data)
                        if continual:
                                episode_list.append(chosen_episode)
                                episode_history = {tmdb_key: episode_list}
                                kodi_utils.set_property('fenskeleton.random_episode_history', json.dumps(episode_history))
                        title, season, episode = self.meta['title'], int(chosen_episode['season']), int(chosen_episode['episode'])
                        watched_info = watched_info_episode(tmdb_id)
                        playcount = get_watched_status_episode(watched_info, (season, episode))
                        query = title + ' S%.2dE%.2d' % (season, episode)
                        display_name = '%s - %dx%.2d' % (title, season, episode)
                        ep_name, plot = chosen_episode['title'], chosen_episode['plot']
                        ep_thumb = chosen_episode.get('thumb', None)
                        try: premiered = adjust_premiered_date(chosen_episode['premiered'], adjust_hours)[1]
                        except: premiered = chosen_episode['premiered']
                        self.meta.update({'media_type': 'episode', 'rootname': display_name, 'season': season, 'ep_name': ep_name, 'ep_thumb': ep_thumb,
                                                        'episode': episode, 'premiered': premiered, 'plot': plot})
                        url_params = {'media_type': 'episode', 'tmdb_id': tmdb_id, 'tvshowtitle': self.meta_get('rootname'), 'season': season, 'episode': episode,
                                                'playcount': playcount, 'autoplay': 'true'}
                        if continual: url_params['random_continual'] = 'true'
                        else: url_params['random'] = 'true'
                        if not first_run:
                                url_params['background'] = 'true'
                                url_params['play_type'] = 'random_continual'
                except: url_params = 'error'
                return self.add_playback_key(url_params)
        def random_next_up_info(self, first_run=True):
                try:
                        from modules import settings

                        current_date, current_time = get_datetime(), get_current_timestamp()
                        watched_indicators_value = watched_indicators()
                        nextep_content = settings.nextep_method()
                        data = get_next_episodes(nextep_content)

                        if settings.nextep_limit_history():
                                data = data[:settings.nextep_limit()]

                        hidden_list = get_hidden_progress_items(watched_indicators_value)
                        if hidden_list:
                                data = [i for i in data if not i['media_ids']['tmdb'] in hidden_list]

                        # A Random Next Up session should move between different shows,
                        # not fall back into a normal binge of the first selected title.
                        # Keep a lightweight session history and exhaust the available
                        # Next Up shows before allowing a repeat.
                        history_key = 'fenskeleton.random_next_up_history'
                        if first_run:
                                show_history = []
                        else:
                                try: show_history = json.loads(kodi_utils.get_property(history_key) or '[]')
                                except: show_history = []
                        unseen_data = [i for i in data if str(i.get('media_ids', {}).get('tmdb')) not in show_history]
                        if unseen_data:
                                data = unseen_data
                        else:
                                show_history = []
                        random.shuffle(data)

                        for ep_data in data:
                                try:
                                        media_ids = ep_data.get('media_ids')
                                        if not media_ids: continue

                                        meta = tvshow_meta('trakt_dict', media_ids, settings.tmdb_api_key(), settings.mpaa_region(), current_date, current_time)
                                        if not meta: continue

                                        watched_info = watched_info_episode(meta.get('tmdb_id'))
                                        season_data = meta.get('season_data')
                                        current_season, current_episode = int(ep_data.get('season')), int(ep_data.get('episode'))
                                        season, episode = get_next(current_season, current_episode, watched_info, season_data, nextep_content)
                                        if not season or not episode: continue

                                        ep_meta = episodes_meta(season, meta)
                                        if not ep_meta: continue

                                        chosen_episode = next((i for i in ep_meta if i['episode'] == episode), None)
                                        if not chosen_episode: continue

                                        episode_date, premiered = adjust_premiered_date(chosen_episode.get('premiered'), date_offset())
                                        if not episode_date or get_datetime() < episode_date: continue

                                        title = meta.get('title')
                                        display_name = '%s - %dx%.2d' % (title, int(season), int(episode))
                                        playcount = get_watched_status_episode(watched_info, (season, episode))

                                        nextep_settings = self.nextep_settings or {}
                                        nextep_settings['random_next_up'] = True

                                        url_params = {
                                                'media_type': 'episode',
                                                'tmdb_id': meta.get('tmdb_id'),
                                                'tvshowtitle': display_name,
                                                'season': season,
                                                'episode': episode,
                                                'playcount': playcount,
                                                'autoplay': 'true',
                                                'play_type': 'autoplay_nextep',
                                                'random_next_up': 'true',
                                                'nextep_settings': nextep_settings,
                                                'watch_count': self.meta_get('watch_count', 1)
                                        }

                                        if not first_run:
                                                url_params['background'] = 'true'
                                        if title:
                                                url_params['custom_title'] = title
                                        if meta.get('year'):
                                                url_params['custom_year'] = meta.get('year')

                                        chosen_tmdb = str(media_ids.get('tmdb'))
                                        if chosen_tmdb and chosen_tmdb not in show_history:
                                                show_history.append(chosen_tmdb)
                                        kodi_utils.set_property(history_key, json.dumps(show_history))
                                        return self.add_playback_key(url_params)
                                except:
                                        pass

                        return 'no_next_episode'
                except:
                        return 'error'

        def play_random_next_up(self):
                url_params = self.random_next_up_info(first_run=True)
                if url_params == 'error': return kodi_utils.notification('Random Next Up Error', 3000)
                elif url_params == 'no_next_episode': return kodi_utils.notification('No Random Next Up Episode Found', 3000)
                return Sources().playback_prep(url_params)



        def play_random(self):
                url_params = self.get_random_episode()
                if url_params == 'error': return kodi_utils.notification('Single Random Play Error', 3000)
                return Sources().playback_prep(url_params)

        def play_random_continual(self, first_run=True):
                url_params = self.get_random_episode(continual=True, first_run=first_run)
                if url_params == 'error': return kodi_utils.notification('Continual Random Play Error', 3000)
                return Sources().playback_prep(url_params)

        def auto_nextep(self):
                url_params = self.next_episode_info()
                if url_params == 'error': return kodi_utils.notification('Next Episode Error', 3000)
                elif url_params == 'no_next_episode': return
                return Sources().playback_prep(url_params)

        def add_playback_key(self, url_params):
                _key = playback_key()
                url_params[_key] = _key
                return url_params

def build_next_episode_manager():
        def _process(item):
                try:
                        listitem = make_listitem()
                        tmdb_id, title = item['media_ids']['tmdb'], item['title']
                        if int(tmdb_id) in hidden_list: display, action = 'Undrop [B]%s[/B] [COLOR=red][DROPPED][/COLOR]' % title, 'undrop'
                        else: display, action = 'Drop [B]%s[/B]' % title, 'drop'
                        url_params = {'mode': mode, 'action': action, 'media_type': 'shows', 'media_id': tmdb_id, 'section': 'dropped'}
                        url = build_url(url_params)
                        listitem.setLabel(display)
                        listitem.setArt({'poster': icon, 'fanart': addon_fanart, 'icon': icon})
                        info_tag = listitem.getVideoInfoTag(True)
                        info_tag.setPlot(' ')
                        append({'listitem': (url, listitem, False), 'sort_title': title})
                except: pass
        handle = int(sys.argv[1])
        make_listitem, build_url, addon_fanart = kodi_utils.make_listitem, kodi_utils.build_url, kodi_utils.get_addon_fanart()
        list_items = []
        append = list_items.append
        indicators = watched_indicators()
        show_list = get_next_episodes(0)
        hidden_list = get_hidden_progress_items(indicators)
        if indicators == 0: icon, mode = kodi_utils.get_icon('folder'), 'hide_unhide_progress_items'
        else: icon, mode = kodi_utils.get_icon('trakt'), 'trakt.hide_unhide_progress_items'
        threads = TaskPool().tasks(_process, show_list, min(len(show_list), max_threads()))
        [i.join() for i in threads]
        item_list = sorted(list_items, key=lambda k: (title_key(k['sort_title'], ignore_articles())), reverse=False)
        item_list = [i['listitem'] for i in item_list]
        kodi_utils.add_items(handle, item_list)
        kodi_utils.set_content(handle, '')
        kodi_utils.end_directory(handle, cacheToDisc=False)
        kodi_utils.set_view_mode('view.main', '')

def single_last_watched_episodes(data):
        seen = set()
        seen_add = seen.add
        return sorted([i for i in sorted(data, key=lambda x: (x['last_played'], x['media_ids']['tmdb'], x['season'], x['episode']), reverse=True)
                                if not (i['media_ids']['tmdb'] in seen or seen_add(i['media_ids']['tmdb']))],
                                key=lambda x: (x['last_played'], x['media_ids']['tmdb'], x['season'], x['episode']), reverse=True)

