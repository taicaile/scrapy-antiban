"""Scarpy Antiban Spider Middleware"""
import logging

from scrapy.http import Request
from twisted.internet import reactor

# from twisted.internet.error import AlreadyCalled, AlreadyCancelled

logger = logging.getLogger(__name__)
META_THROTTLE_KEY = "pre_request_banned"
DELAY_TIME_START = 60
MIN_TIME = 0.1
INCREASE_RATIO = 1.5


class SlotState:
    """slot state"""

    def __init__(self, key, slot) -> None:
        self.key = key
        self.slot = slot
        self.banned_num = 0
        self.successed_num = 0

        self.is_delayed = False

        self.pause_time = DELAY_TIME_START
        self.is_paused = False

    def slot_pause_once(self):
        if not self.is_paused:
            self.slot.lastseen += self.pause_time
            reactor.callLater(self.pause_time, self.reset)

    def slot_delay_inc_once(self):
        if not self.is_delayed:
            self.slot.delay = max(MIN_TIME, self.slot.delay) * INCREASE_RATIO

    def reset(self):
        self.banned_num = 0
        self.successed_num = 0
        logger.warning("slotstate: %s reset", self)

    def __repr__(self) -> str:
        return f"{self.key},{self.banned_num},{self.successed_num},{self.slot}"

    __str__ = __repr__


class ThrottleMiddleware:
    """Throttle control middleware"""

    def __init__(self, crawler, verbose=True):
        self.crawler = crawler
        self.verbose = verbose
        self.slotstates = {}

    def get_slotstate(self, request) -> "SlotState":
        key = self._get_slot_key(request)
        if key not in self.slotstates:
            slot = self._get_slot_key(key)
            self.slotstates[key] = SlotState(key, slot)
        return self.slotstates[key]

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        verbose = settings.getbool("THROTTLE_VERBOSESTATUS", True)
        return cls(crawler, verbose)

    def _get_slot_key(self, request):
        # pylint: disable=protected-access
        return self.crawler.engine.downloader._get_slot_key(request)

    def _get_slot(self, key):
        # pylint: disable=protected-access
        # key = request.meta.get("download_slot")
        return self.crawler.engine.downloader.slots.get(key)

    def process_spider_output(self, response, result, spider):
        """process_spider_output"""
        del response, spider

        def _filter(request):
            if isinstance(request, Request):
                is_banned = request.meta.get(META_THROTTLE_KEY, None)
                slotstate = self.get_slotstate(request)
                if not is_banned:
                    slotstate.successed_num += 1
                else:
                    slotstate.banned_num += 1
                    slotstate.slot_pause_once()
                logger.info("%s,%s", slotstate.successed_num, slotstate.banned_num)
                # if there are both successed and failed request,
                # the slot delay time needs to be increased.
                if slotstate.successed_num > 0 and slotstate.banned_num > 0:
                    slotstate.slot_delay_inc_once()

            # return true always
            return True

        return (r for r in result or () if _filter(r))
