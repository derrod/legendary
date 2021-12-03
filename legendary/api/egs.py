# !/usr/bin/env python
# coding: utf-8

import requests
import requests.adapters
import logging

from requests.auth import HTTPBasicAuth

from legendary.models.exceptions import InvalidCredentialsError
from legendary.models.gql import *


class EPCAPI:
    _user_agent = 'UELauncher/11.0.1-14907503+++Portal+Release-Live Windows/10.0.19041.1.256.64bit'
    _store_user_agent = 'EpicGamesLauncher/11.0.1-14907503+++Portal+Release-Live'
    # required for the oauth request
    _user_basic = '34a02cf8f4414e29b15921876da36f9a'
    _pw_basic = 'daafbccc737745039dffe53d94fc76cf'
    _label = 'Live-EternalKnight'

    _oauth_host = 'account-public-service-prod03.ol.epicgames.com'
    _launcher_host = 'launcher-public-service-prod06.ol.epicgames.com'
    _entitlements_host = 'entitlement-public-service-prod08.ol.epicgames.com'
    _catalog_host = 'catalog-public-service-prod06.ol.epicgames.com'
    _ecommerce_host = 'ecommerceintegration-public-service-ecomprod02.ol.epicgames.com'
    _datastorage_host = 'datastorage-public-service-liveegs.live.use1a.on.epicgames.com'
    _library_host = 'library-service.live.use1a.on.epicgames.com'
    _store_gql_host = 'store-launcher.epicgames.com'

    def __init__(self, lc='en', cc='US'):
        self.log = logging.getLogger('EPCAPI')

        self.session = requests.session()
        self.session.headers['User-Agent'] = self._user_agent
        # increase maximum pool size for multithreaded metadata requests
        self.session.mount('https://', requests.adapters.HTTPAdapter(pool_maxsize=16))

        self.unauth_session = requests.session()
        self.unauth_session.headers['User-Agent'] = self._user_agent

        self._oauth_basic = HTTPBasicAuth(self._user_basic, self._pw_basic)

        self.access_token = None
        self.user = None

        self.language_code = lc
        self.country_code = cc

    def update_egs_params(self, egs_params):
        # update user-agent
        if version := egs_params['version']:
            self._user_agent = f'UELauncher/{version} Windows/10.0.19041.1.256.64bit'
            self._user_agent = f'EpicGamesLauncher/{version}'
            self.session.headers['User-Agent'] = self._user_agent
            self.unauth_session.headers['User-Agent'] = self._user_agent
        # update label
        if label := egs_params['label']:
            self._label = label
        # update client credentials
        if 'client_id' in egs_params and 'client_secret' in egs_params:
            self._user_basic = egs_params['client_id']
            self._pw_basic = egs_params['client_secret']
            self._oauth_basic = HTTPBasicAuth(self._user_basic, self._pw_basic)

    def resume_session(self, session):
        self.session.headers['Authorization'] = f'bearer {session["access_token"]}'
        r = self.session.get(f'https://{self._oauth_host}/account/api/oauth/verify')
        if r.status_code >= 500:
            r.raise_for_status()

        j = r.json()
        if 'errorMessage' in j:
            self.log.warning(f'Login to EGS API failed with errorCode: {j["errorCode"]}')
            raise InvalidCredentialsError(j['errorCode'])

        # update other data
        session.update(j)
        self.user = session
        return self.user

    def start_session(self, refresh_token: str = None, exchange_token: str = None) -> dict:
        if refresh_token:
            params = dict(grant_type='refresh_token',
                          refresh_token=refresh_token,
                          token_type='eg1')
        elif exchange_token:
            params = dict(grant_type='exchange_code',
                          exchange_code=exchange_token,
                          token_type='eg1')
        else:
            raise ValueError('At least one token type must be specified!')

        r = self.session.post(f'https://{self._oauth_host}/account/api/oauth/token',
                              data=params, auth=self._oauth_basic)
        # Only raise HTTP exceptions on server errors
        if r.status_code >= 500:
            r.raise_for_status()

        j = r.json()
        if 'error' in j:
            self.log.warning(f'Login to EGS API failed with errorCode: {j["errorCode"]}')
            raise InvalidCredentialsError(j['errorCode'])

        self.user = j
        self.session.headers['Authorization'] = f'bearer {self.user["access_token"]}'
        return self.user

    def invalidate_session(self):  # unused
        r = self.session.delete(f'https://{self._oauth_host}/account/api/oauth/sessions/kill/{self.access_token}')

    def get_game_token(self):
        r = self.session.get(f'https://{self._oauth_host}/account/api/oauth/exchange')
        r.raise_for_status()
        return r.json()

    def get_ownership_token(self, namespace, catalog_item_id):
        user_id = self.user.get('account_id')
        r = self.session.post(f'https://{self._ecommerce_host}/ecommerceintegration/api/public/'
                              f'platforms/EPIC/identities/{user_id}/ownershipToken',
                              data=dict(nsCatalogItemId=f'{namespace}:{catalog_item_id}'))
        r.raise_for_status()
        return r.content

    def get_external_auths(self):
        user_id = self.user.get('account_id')
        r = self.session.get(f'https://{self._oauth_host}/account/api/public/account/{user_id}/externalAuths')
        r.raise_for_status()
        return r.json()

    def get_game_assets(self, platform='Windows', label='Live'):
        r = self.session.get(f'https://{self._launcher_host}/launcher/api/public/assets/{platform}',
                             params=dict(label=label))
        r.raise_for_status()
        return r.json()

    def get_game_manifest(self, namespace, catalog_item_id, app_name, platform='Windows', label='Live'):
        r = self.session.get(f'https://{self._launcher_host}/launcher/api/public/assets/v2/platform'
                             f'/{platform}/namespace/{namespace}/catalogItem/{catalog_item_id}/app'
                             f'/{app_name}/label/{label}')
        r.raise_for_status()
        return r.json()

    def get_launcher_manifests(self, platform='Windows', label=None):
        r = self.session.get(f'https://{self._launcher_host}/launcher/api/public/assets/v2/platform/'
                             f'{platform}/launcher',
                             params=dict(label=label if label else self._label))
        r.raise_for_status()
        return r.json()

    def get_user_entitlements(self):
        user_id = self.user.get('account_id')
        r = self.session.get(f'https://{self._entitlements_host}/entitlement/api/account/{user_id}/entitlements',
                             params=dict(start=0, count=5000))
        r.raise_for_status()
        return r.json()

    def get_game_info(self, namespace, catalog_item_id, timeout=None):
        r = self.session.get(f'https://{self._catalog_host}/catalog/api/shared/namespace/{namespace}/bulk/items',
                             params=dict(id=catalog_item_id, includeDLCDetails=True, includeMainGameDetails=True,
                                         country=self.country_code, locale=self.language_code),
                             timeout=timeout)
        r.raise_for_status()
        return r.json().get(catalog_item_id, None)

    def get_library_items(self, include_metadata=True):
        records = []
        r = self.session.get(f'https://{self._library_host}/library/api/public/items',
                             params=dict(includeMetadata=include_metadata))
        r.raise_for_status()
        j = r.json()
        records.extend(j['records'])

        # Fetch remaining library entries as long as there is a cursor
        while cursor := j['responseMetadata'].get('nextCursor', None):
            r = self.session.get(f'https://{self._library_host}/library/api/public/items',
                                 params=dict(includeMetadata=include_metadata, cursor=cursor))
            r.raise_for_status()
            j = r.json()
            records.extend(j['records'])

        return records

    def get_user_cloud_saves(self, app_name='', manifests=False, filenames=None):
        if app_name and manifests:
            app_name += '/manifests/'
        elif app_name:
            app_name += '/'

        user_id = self.user.get('account_id')

        if filenames:
            r = self.session.post(f'https://{self._datastorage_host}/api/v1/access/egstore/savesync/'
                                  f'{user_id}/{app_name}', json=dict(files=filenames))
        else:
            r = self.session.get(f'https://{self._datastorage_host}/api/v1/access/egstore/savesync/'
                                 f'{user_id}/{app_name}')
        r.raise_for_status()
        return r.json()
    
    def create_game_cloud_saves(self, app_name, filenames):
        return self.get_user_cloud_saves(app_name, filenames=filenames)

    def delete_game_cloud_save_file(self, path):
        url = f'https://{self._datastorage_host}/api/v1/data/egstore/{path}'
        r = self.session.delete(url)
        r.raise_for_status()

    def store_get_uplay_codes(self):
        user_id = self.user.get('account_id')
        r = self.session.post(f'https://{self._store_gql_host}/graphql',
                              json=dict(query=uplay_codes_query,
                                        variables=dict(accountId=user_id)))
        r.raise_for_status()
        return r.json()

    def store_claim_uplay_code(self, uplay_id, game_id):
        user_id = self.user.get('account_id')
        r = self.session.post(f'https://{self._store_gql_host}/graphql',
                              json=dict(query=uplay_claim_query,
                                        variables=dict(accountId=user_id,
                                                       uplayAccountId=uplay_id,
                                                       gameId=game_id)))
        r.raise_for_status()
        return r.json()

    def store_redeem_uplay_codes(self, uplay_id):
        user_id = self.user.get('account_id')
        r = self.session.post(f'https://{self._store_gql_host}/graphql',
                              json=dict(query=uplay_redeem_query,
                                        variables=dict(accountId=user_id,
                                                       uplayAccountId=uplay_id)))
        r.raise_for_status()
        return r.json()
