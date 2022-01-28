"""Scarpy Antiban Spider Middleware"""

import logging

from scrapy.http import Request
from twisted.internet import reactor
from twisted.internet.error import AlreadyCalled, AlreadyCancelled

logger = logging.getLogger(__name__)
META_THROTTLE_KEY = "pre_request_banned"
DELAY_TIME_START = 60
MIN_TIME = 0.1
INCREASE_RATIO = 1.5


class ThrottleMiddleware:
    """Throttle control middleware"""

    def __init__(self, crawler, verbose=True):
        self.crawler = crawler
        self.verbose = verbose
        self.engine_resume_task = None
        self.engine_pause_time = DELAY_TIME_START
        self.banned_num = 0
        self.successed_num = 0
        self.slots_delay = {}

    def engine_status_reset(self):
        """reset counter"""
        self.banned_num = 0
        self.successed_num = 0

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        verbose = settings.getbool("THROTTLE_VERBOSESTATUS", True)
        return cls(crawler, verbose)

    def _get_slot(self, request):
        key = request.meta.get("download_slot")
        return key, self.crawler.engine.downloader.slots.get(key)

    def engine_pause(self):
        """pause engine"""
        # if the first request after engine pause is still banned,
        # the engine pause time needs to be increased.
        if self.successed_num == 0 and self.banned_num == 1:
            self.engine_pause_time = int(self.engine_pause_time * INCREASE_RATIO)

        resume_need_created = True
        if self.engine_resume_task and self.engine_resume_task.active():
            try:
                self.engine_resume_task.reset(self.engine_pause_time)
                resume_need_created = False
                logger.warning(
                    "engine pause timer reset to %s seconds",
                    self.engine_pause_time,
                )
            except (AlreadyCancelled, AlreadyCalled):
                pass

        if resume_need_created:
            # create new one
            logger.warning(
                "create a new engine pause task for %s seconds",
                self.engine_pause_time,
            )
            self.crawler.engine.pause()
            self.engine_resume_task = reactor.callLater(
                self.engine_pause_time, self.engine_resume
            )

    def engine_resume(self):
        """engine resume"""
        for key, newdelay in self.slots_delay.items():
            slot = self.crawler.engine.downloader.slots.get(key)
            if not slot:
                logger.warning("no slot found for key: %s", key)
                return
            slot.delay = newdelay
            logger.warning("increase slot delay: %s", slot)

        # reset status
        self.engine_status_reset()
        self.slots_delay = {}

        # engine resume
        self.crawler.engine.unpause()
        logger.warning(
            "engine resumed after stopped %s seconds", self.engine_pause_time
        )

    def slot_delay_inc_once(self, request):
        """increase slot delay time"""
        key, slot = self._get_slot(request)
        if not key or not slot:
            logger.warning("no key or slot found for current request: %s", request)
            return
        self.slots_delay[key] = max(MIN_TIME, slot.delay) * INCREASE_RATIO
        logger.warning("update slot: %s key, to %s", key, self.slots_delay[key])

    def process_spider_output(self, response, result, spider):
        """process_spider_output"""

        del response, spider

        def _filter(request):
            if isinstance(request, Request):
                is_banned = request.meta.get(META_THROTTLE_KEY, None)
                if not is_banned:
                    self.successed_num += 1
                else:
                    self.banned_num += 1
                    # banned, stop the engine
                    self.engine_pause()
                # if there are both successed and failed request,
                # the slot delay time needs to be increased.
                if self.successed_num > 0 and self.banned_num > 0:
                    self.slot_delay_inc_once(request)

            # return true always
            return True

        return (r for r in result or () if _filter(r))
