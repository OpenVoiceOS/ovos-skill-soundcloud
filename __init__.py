from os.path import join, dirname
from typing import Iterable, Union

from json_database import JsonStorageXDG
from nuvem_de_som import SoundCloud
from ovos_utils import classproperty
from ovos_utils.log import LOG
from ovos_utils.ocp import MediaType, PlaybackType, Playlist, PluginStream, dict2entry
from ovos_utils.parse import fuzzy_match, MatchStrategy
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill, \
    ocp_search


class SoundCloudSkill(OVOSCommonPlaybackSkill):
    def __init__(self, *args, **kwargs):
        self._search_cache = JsonStorageXDG("soundcloud.search.history",
                                            subfolder="common_play")
        self._search_cache.clear()
        super().__init__(supported_media=[MediaType.MUSIC, MediaType.GENERIC],
                         skill_icon=join(dirname(__file__), "soundcloud.png"),
                         skill_voc_filename="soundcloud_skill",
                         *args, **kwargs)

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(internet_before_load=True,
                                   network_before_load=True,
                                   gui_before_load=False,
                                   requires_internet=True,
                                   requires_network=True,
                                   requires_gui=False,
                                   no_internet_fallback=False,
                                   no_network_fallback=False,
                                   no_gui_fallback=True)

    def initialize(self):
        if "cache" not in self.settings:
            self.settings["cache"] = True
        if "refresh_cache" not in self.settings:
            self.settings["refresh_cache"] = True

        if self.settings["refresh_cache"]:
            self._search_cache.clear()
            self._search_cache.store()

        if "artists" not in self._search_cache:
            self._search_cache["artists"] = {}
        if "sets" not in self._search_cache:
            self._search_cache["sets"] = {}
        if "tracks" not in self._search_cache:
            self._search_cache["tracks"] = {}

    # score
    @staticmethod
    def calc_score(phrase, match, base_score=0, idx=0, searchtype="tracks"):
        # idx represents the order from soundcloud
        score = base_score

        title_score = 100 * fuzzy_match(
            phrase.lower().strip(),
            match["title"].lower().strip(),
            strategy=MatchStrategy.DAMERAU_LEVENSHTEIN_SIMILARITY)
        artist_score = 100 * fuzzy_match(
            phrase.lower().strip(),
            match["artist"].lower().strip(),
            strategy=MatchStrategy.DAMERAU_LEVENSHTEIN_SIMILARITY)
        if searchtype == "artists":
            score += artist_score
        elif searchtype == "tracks":
            if artist_score >= 75:
                score += artist_score * 0.5 + title_score * 0.5
            else:
                score += title_score * 0.85 + artist_score * 0.15
            # TODO score penalty based on track length,
            #  longer -> less likely to be a song
            score -= idx * 2  # - 2% as we go down the results list
        else:
            if artist_score >= 85:
                score += artist_score * 0.85 + title_score * 0.15
            elif artist_score >= 70:
                score += artist_score * 0.7 + title_score * 0.3
            elif artist_score >= 50:
                score += title_score * 0.5 + artist_score * 0.5
            else:
                score += title_score * 0.7 + artist_score * 0.3

        # LOG.debug(f"type: {searchtype} score: {score} artist:
        # {match['artist']} title: {match['title']}")
        score = min((100, score))
        return score

    def search_soundcloud(self, phrase, searchtype="tracks") -> Iterable[Union[PluginStream, Playlist]]:
        # cache results for speed in repeat queries
        if self.settings["cache"] and phrase in self._search_cache[searchtype]:
            for r in self._search_cache[searchtype][phrase]:
                yield dict2entry(r)
        else:
            try:
                # NOTE: stream will be extracted again for playback
                # but since they are not valid for very long this is needed
                # otherwise on click/next/prev it will have expired
                # it also means we can safely cache results!
                results = []
                if searchtype == "tracks":
                    for r in SoundCloud.search_tracks(phrase):
                        if r["duration"] <= 60:
                            continue  # filter previews
                        entry = PluginStream(
                            extractor_id="ydl",
                            stream=r["url"],
                            title=r["title"],
                            artist=r["artist"],
                            match_confidence=self.calc_score(phrase, r,
                                                             searchtype=searchtype,
                                                             idx=len(results)),
                            media_type=MediaType.MUSIC,
                            playback=PlaybackType.AUDIO,
                            skill_id=self.skill_id,
                            skill_icon=self.skill_icon,
                            length=r["duration"] * 1000,  # seconds to milliseconds
                            image=r["image"],
                        )
                        yield entry
                        results.append(entry)

                elif searchtype == "artists":
                    n = 0
                    for a in SoundCloud.search_people(phrase):
                        pl = Playlist(title="")
                        for idx, v in enumerate(a["tracks"]):
                            if v["duration"] <= 60:
                                continue  # filter previews
                            entry = PluginStream(
                                extractor_id="ydl",
                                stream=v["url"],
                                title=v["title"],
                                artist=v["artist"],
                                match_confidence=self.calc_score(phrase, v,
                                                                 searchtype="artists",
                                                                 idx=idx),
                                media_type=MediaType.MUSIC,
                                playback=PlaybackType.AUDIO,
                                skill_id=self.skill_id,
                                skill_icon=self.skill_icon,
                                length=v["duration"] * 1000,  # seconds to milliseconds
                                image=v["image"],
                            )
                            if not pl.title:
                                pl.title = entry.artist + " (Featured Tracks)"
                            pl.append(entry)
                        if not pl:
                            continue
                        conf = sum(e.match_confidence for e in pl) / len(pl)
                        pl.match_confidence = min((100, conf))
                        yield pl
                        results.append(pl)

                    n += 1

                elif searchtype == "sets":
                    n = 0
                    for s in SoundCloud.search_sets(phrase):
                        pl = Playlist(title=s["title"] + " (Playlist)")

                        for idx, v in enumerate(s["tracks"]):
                            if v["duration"] <= 60:
                                continue  # filter previews

                            entry = PluginStream(
                                extractor_id="ydl",
                                stream=v["url"],
                                title=v["title"],
                                artist=v["artist"],
                                match_confidence=self.calc_score(phrase, v,
                                                                 searchtype="sets",
                                                                 idx=idx),
                                media_type=MediaType.MUSIC,
                                playback=PlaybackType.AUDIO,
                                skill_id=self.skill_id,
                                skill_icon=self.skill_icon,
                                length=v["duration"] * 1000,  # seconds to milliseconds
                                image=v["image"],
                            )
                            pl.append(entry)
                        if not pl:
                            continue
                        yield pl
                        results.append(pl)

                    n += 1

                else:
                    for r in SoundCloud.search(phrase):
                        if r["duration"] < 60:
                            continue  # filter previews
                        entry = PluginStream(
                            extractor_id="ydl",
                            stream=r["url"],
                            title=r["title"],
                            artist=r["artist"],
                            match_confidence=self.calc_score(phrase, r,
                                                             searchtype=searchtype,
                                                             idx=len(results)),
                            media_type=MediaType.MUSIC,
                            playback=PlaybackType.AUDIO,
                            skill_id=self.skill_id,
                            skill_icon=self.skill_icon,
                            length=r["duration"] * 1000,  # seconds to milliseconds
                            image=r["image"],
                        )
                        yield entry
                        results.append(entry)
            except Exception as e:
                return []
            if self.settings["cache"]:
                self._search_cache[searchtype][phrase] = [e.as_dict for e in results]
                self._search_cache.store()

    @ocp_search()
    def search_artists(self, phrase, media_type=MediaType.GENERIC) -> Iterable[Playlist]:
        # match the request media_type
        base_score = 0
        if media_type == MediaType.MUSIC:
            base_score += 15

        if self.voc_match(phrase, "soundcloud"):
            # explicitly requested soundcloud
            base_score += 50
            phrase = self.remove_voc(phrase, "soundcloud")

        LOG.debug("searching soundcloud artists")
        for pl in self.search_soundcloud(phrase, "artists"):
            yield pl

    #@ocp_search()
    def search_sets(self, phrase, media_type=MediaType.GENERIC) -> Iterable[Playlist]:
        # match the request media_type
        base_score = 0
        if media_type == MediaType.MUSIC:
            base_score += 15

        if self.voc_match(phrase, "soundcloud"):
            # explicitly requested soundcloud
            base_score += 30
            phrase = self.remove_voc(phrase, "soundcloud")

        LOG.debug("searching soundcloud sets")
        for pl in self.search_soundcloud(phrase, "sets"):
            yield pl

    #@ocp_search()
    def search_tracks(self, phrase, media_type=MediaType.GENERIC) -> Iterable[PluginStream]:
        # match the request media_type
        base_score = 0
        if media_type == MediaType.MUSIC:
            base_score += 10

        if self.voc_match(phrase, "soundcloud"):
            # explicitly requested soundcloud
            base_score += 30
            phrase = self.remove_voc(phrase, "soundcloud")

        LOG.debug("searching soundcloud tracks")
        for r in self.search_soundcloud(phrase, searchtype="tracks"):
            score = r.match_confidence
            if score < 35:
                continue
            # crude attempt at filtering non music / preview tracks
            if r.length < 60:
                continue
            # we might still get podcasts, would be nice to handle that better
            if r.length > 60 * 45:  # >45 min is probably not music :shrug:
                continue
            yield r


if __name__ == "__main__":
    from ovos_utils.messagebus import FakeBus

    LOG.set_level("DEBUG")

    s = SoundCloudSkill(bus=FakeBus(), skill_id="t.fake")

    for r in s.search_artists("piratech", MediaType.MUSIC):
        print(r)
        # Playlist(title='Piratech (Featured Tracks)', artist='', position=0, image='', match_confidence=100, skill_id='ovos.common_play', skill_icon='', playback=<PlaybackType.UNDEFINED: 100>, media_type=<MediaType.GENERIC: 0>)
        # Playlist(title='piratech (Featured Tracks)', artist='', position=0, image='', match_confidence=100, skill_id='ovos.common_play', skill_icon='', playback=<PlaybackType.UNDEFINED: 100>, media_type=<MediaType.GENERIC: 0>)
        # Playlist(title='PARATECH (Featured Tracks)', artist='', position=0, image='', match_confidence=87.5, skill_id='ovos.common_play', skill_icon='', playback=<PlaybackType.UNDEFINED: 100>, media_type=<MediaType.GENERIC: 0>)
        # Playlist(title='piratech_corexd (Featured Tracks)', artist='', position=0, image='', match_confidence=53.333333333333336, skill_id='ovos.common_play', skill_icon='', playback=<PlaybackType.UNDEFINED: 100>, media_type=<MediaType.GENERIC: 0>)
        # Playlist(title='Tezin Pirateuh Tribe (Featured Tracks)', artist='', position=0, image='', match_confidence=35.0, skill_id='ovos.common_play', skill_icon='', playback=<PlaybackType.UNDEFINED: 100>, media_type=<MediaType.GENERIC: 0>)
        # Playlist(title='JoR (Featured Tracks)', artist='', position=0, image='', match_confidence=12.5, skill_id='ovos.common_play', skill_icon='', playback=<PlaybackType.UNDEFINED: 100>, media_type=<MediaType.GENERIC: 0>)
