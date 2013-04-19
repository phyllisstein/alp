import alp.core as core
from bs4 import BeautifulSoup
import requests
import requests_cache


class Request(object):
    def __init__(self, url, payload=None, post=False, cache_for=None):
        cacheName = core.cache("requests_cache")
        if cache_for != None and cache_for < 0:
            exp = None
        else:
            exp = cache_for or 24 * (60^3)
        requests_cache.install_cache(cacheName, expire_after=exp)
        if payload:
            self.request = requests.get(url, params=payload) if not post else requests.post(url, data=payload)
        else:
            self.request = requests.get(url)

    def souper(self):
        if self.request.status_code == requests.codes.ok:
            return BeautifulSoup(self.request.text)
        else:
            self.request.raise_for_status()

    def clear_cache(self):
        requests_cache.clear()
