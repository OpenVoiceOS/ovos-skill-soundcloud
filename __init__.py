from os.path import join, dirname
from ovos_utils.log import LOG
from json_database import JsonStorageXDG
from nuvem_de_som import SoundCloud
from ovos_utils.parse import fuzzy_match
from ovos_plugin_common_play.ocp import MediaType, \
    PlaybackType
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill, \
    ocp_search


class SoundCloudSkill(OVOSCommonPlaybackSkill):
    def __init__(self):
        super(SoundCloudSkill, self).__init__("SoundCloud")
        self.supported_media = [MediaType.GENERIC,
                                MediaType.MUSIC]
        if "cache" not in self.settings:
            self.settings["cache"] = True
        if "refresh_cache" not in self.settings:
            self.settings["refresh_cache"] = True

        self._search_cache = JsonStorageXDG("soundcloud.search.history",
                                            subfolder="common_play")
        if self.settings["refresh_cache"]:
            self._search_cache.clear()
            self._search_cache.store()

        if "artists" not in self._search_cache:
            self._search_cache["artists"] = {}
        if "sets" not in self._search_cache:
            self._search_cache["sets"] = {}
        if "tracks" not in self._search_cache:
            self._search_cache["tracks"] = {}
        self.skill_icon = join(dirname(__file__), "ui", "soundcloud.png")

    # score
    @staticmethod
    def calc_score(phrase, match, base_score=0, idx=0, searchtype="tracks"):
        # idx represents the order from soundcloud
        score = base_score

        title_score = 100 * fuzzy_match(phrase.lower().strip(),
                                        match["title"].lower().strip())
        artist_score = 100 * fuzzy_match(phrase.lower().strip(),
                                         match["artist"].lower().strip())
        if searchtype == "artists":
            score += artist_score
        elif searchtype == "tracks":
            if artist_score >= 75:
                score += artist_score * 0.5 + title_score * 0.5
            else:
                score += title_score * 0.85 + artist_score * 0.15
        else:
            if artist_score >= 85:
                score += artist_score * 0.85 + title_score * 0.15
            elif artist_score >= 70:
                score += artist_score * 0.7 + title_score * 0.3
            elif artist_score >= 50:
                score += title_score * 0.5 + artist_score * 0.5
            else:
                score += title_score * 0.7 + artist_score * 0.3

        #LOG.debug(f"type: {searchtype} score: {score} artist:
        # {match['artist']} title: {match['title']}")
        score = min((100, score))
        score -= idx * 5  # - 5% as we go down the results list
        return score

    def search_soundcloud(self, phrase, searchtype="tracks"):
        # cache results for speed in repeat queries
        if self.settings["cache"] and phrase in self._search_cache[searchtype]:
            for r in self._search_cache[searchtype][phrase]:
                yield r
        else:
            try:
                # NOTE: stream will be extracted again for playback
                # but since they are not valid for very long this is needed
                # otherwise on click/next/prev it will have expired
                # it also means we can safely cache results!
                results = []
                if searchtype == "tracks":
                    for r in SoundCloud.search_tracks(phrase):
                        r["uri"] = "soundcloud//" + r["url"]
                        r["match_confidence"] = self.calc_score(
                            phrase, r, searchtype=searchtype, idx=len(results))
                        yield r
                        results.append(r)
                elif searchtype == "artists":
                    n = 0
                    for a in SoundCloud.search_people(phrase):
                        for r in a["tracks"]:
                            # - 15% score for each artist
                            conf = self.calc_score(phrase, r,
                                                   searchtype=searchtype,
                                                   idx=len(results)) - n * 15
                            r["uri"] = "soundcloud//" + r["url"]
                            r["match_confidence"] = conf
                            yield r
                            results.append(r)
                        n += 1

                elif searchtype == "sets":
                    n = 0
                    for s in SoundCloud.search_sets(phrase):
                        for r in s["tracks"]:
                            # - 15% score for each set
                            conf = self.calc_score(phrase, r,
                                                   searchtype=searchtype,
                                                   idx=len(results)) - n * 15
                            r["uri"] = "soundcloud//" + r["url"]
                            r["match_confidence"] = conf
                            yield r
                            results.append(r)
                        n += 1
                else:
                    for r in SoundCloud.search(phrase):
                        r["uri"] = "soundcloud//" + r["url"]
                        r["match_confidence"] = self.calc_score(
                            phrase, r, searchtype=searchtype, idx=len(results))
                        yield r
                        results.append(r)
            except Exception as e:
                # soundcloud can break at any time...
                self.log.error("soundcloud search failed!")
                self.log.exception(e)
                return []
            if self.settings["cache"]:
                self._search_cache[searchtype][phrase] = results
                self._search_cache.store()

    @ocp_search()
    def search_tracks(self, phrase, media_type=MediaType.GENERIC):
        # match the request media_type
        base_score = 0
        if media_type == MediaType.MUSIC:
            base_score += 15

        if self.voc_match(phrase, "soundcloud"):
            # explicitly requested soundcloud
            base_score += 30
            phrase = self.remove_voc(phrase, "soundcloud")

        #LOG.debug("searching soundcloud tracks")
        for r in self.search_soundcloud(phrase, searchtype="tracks"):
            score = r["match_confidence"]
            if score < 35:
                continue
            # crude attempt at filtering non music / preview tracks
            # we might still get podcasts, would be nice to handle that in separate
            if r["duration"] < 60:
                continue

            yield {
                "match_confidence": score + base_score,
                "media_type": MediaType.MUSIC,
                "length": r["duration"] * 1000,  # seconds to milliseconds
                "uri": r["uri"],
                "playback": PlaybackType.AUDIO,
                "image": r["image"],
                "bg_image": r["image"],
                "skill_icon": self.skill_icon,
                "title": r["title"],
                "artist": r["artist"],
                "skill_id": self.skill_id
            }

    @ocp_search()
    def search_artists(self, phrase, media_type=MediaType.GENERIC):
        # match the request media_type
        base_score = 0
        if media_type == MediaType.MUSIC:
            base_score += 15

        if self.voc_match(phrase, "soundcloud"):
            # explicitly requested soundcloud
            base_score += 50
            phrase = self.remove_voc(phrase, "soundcloud")
        #LOG.debug("searching soundcloud artists")
        for r in self.search_soundcloud(phrase, searchtype="artists"):
            score = r["match_confidence"]
            if score < 35:
                continue
            # crude attempt at filtering non music / preview tracks
            # we might still get podcasts, would be nice to handle that in separate
            if r["duration"] < 60:
                continue

            yield {
                "match_confidence": score + base_score,
                # TODO this can actuall go above 100
                "media_type": MediaType.MUSIC,
                "length": r["duration"] * 1000,  # seconds to milliseconds
                "uri": r["uri"],
                "playback": PlaybackType.AUDIO,
                "image": r["image"],
                "bg_image": r["image"],
                "skill_icon": self.skill_icon,
                "title": r["title"],
                "artist": r["artist"],
                "skill_id": self.skill_id
            }

    @ocp_search()
    def search_sets(self, phrase, media_type=MediaType.GENERIC):
        # match the request media_type
        base_score = 0
        if media_type == MediaType.MUSIC:
            base_score += 15

        if self.voc_match(phrase, "soundcloud"):
            # explicitly requested soundcloud
            base_score += 30
            phrase = self.remove_voc(phrase, "soundcloud")
        #LOG.debug("searching soundcloud sets")
        for r in self.search_soundcloud(phrase, searchtype="sets"):
            score = r["match_confidence"]
            if score < 35:
                continue
            # crude attempt at filtering non music / preview tracks
            # we might still get podcasts, would be nice to handle that in separate
            if r["duration"] < 60:
                continue

            yield {
                "match_confidence": score + base_score ,
                # TODO this can actuall go above 100
                "media_type": MediaType.MUSIC,
                "length": r["duration"] * 1000,  # seconds to milliseconds
                "uri": r["uri"],
                "playback": PlaybackType.AUDIO,
                "image": r["image"],
                "bg_image": r["image"],
                "skill_icon": self.skill_icon,
                "title": r["title"],
                "artist": r["artist"],
                "skill_id": self.skill_id
            }


def create_skill():
    return SoundCloudSkill()
