# !/usr/bin/env python
# coding: utf-8

import legendary
import requests
import logging


class LGDAPI:
    _user_agent = f'Legendary/{legendary.__version__}'
    _api_host = 'legendary.rodney.io'

    def __init__(self):
        self.session = requests.session()
        self.log = logging.getLogger('LGDAPI')
        self.session.headers['User-Agent'] = self._user_agent

    def get_version_information(self):
        r = self.session.get(f'https://{self._api_host}/version.json',
                             timeout=10.0)
        r.raise_for_status()
        return r.json()
