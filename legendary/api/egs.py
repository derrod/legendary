# !/usr/bin/env python
# coding: utf-8

import urllib.parse

import requests
import requests.adapters
import logging

from requests.auth import HTTPBasicAuth

from legendary.models.exceptions import InvalidCredentialsError
from legendary.models.gql import *


class EPCAPI:
    _user_agent = 'UELauncher/11.0.1-14907503+++Portal+Release-Live Windows/10.0.19041.1.256.64bit'
    _store_user_agent = 'EpicGamesLauncher/14.0.8-22004686+++Portal+Release-Live'
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
    # Using the actual store host with a user-agent newer than 14.0.8 leads to a CF verification page,
    # but the dedicated graphql host works fine.
    # _store_gql_host = 'launcher.store.epicgames.com'
    _store_gql_host = 'graphql.epicgames.com'
    _artifact_service_host = 'artifact-public-service-prod.beee.live.use1a.on.epicgames.com'

    def __init__(self, lc='en', cc='US', timeout=10.0):
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

        self.request_timeout = timeout if timeout > 0 else None

    def get_auth_url(self):
        login_url = 'https://www.epicgames.com/id/login?redirectUrl='
        redirect_url = f'https://www.epicgames.com/id/api/redirect?clientId={self._user_basic}&responseType=code'
        return login_url + urllib.parse.quote(redirect_url)

    def update_egs_params(self, egs_params):
        # update user-agent
        if version := egs_params['version']:
            self._user_agent = f'UELauncher/{version} Windows/10.0.19041.1.256.64bit'
            self._store_user_agent = f'EpicGamesLauncher/{version}'
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
        r = self.session.get(f'https://{self._oauth_host}/account/api/oauth/verify',
                             timeout=self.request_timeout)
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

    def start_session(self, refresh_token: str = None, exchange_token: str = None,
                      authorization_code: str = None, client_credentials: bool = False) -> dict:
        if refresh_token:
            params = dict(grant_type='refresh_token',
                          refresh_token=refresh_token,
                          token_type='eg1')
        elif exchange_token:
            params = dict(grant_type='exchange_code',
                          exchange_code=exchange_token,
                          token_type='eg1')
        elif authorization_code:
            params = dict(grant_type='authorization_code',
                          code=authorization_code,
                          token_type='eg1')
        elif client_credentials:
            params = dict(grant_type='client_credentials',
                          token_type='eg1')
        else:
            raise ValueError('At least one token type must be specified!')

        r = self.session.post(f'https://{self._oauth_host}/account/api/oauth/token',
                              data=params, auth=self._oauth_basic,
                              timeout=self.request_timeout)
        # Only raise HTTP exceptions on server errors
        if r.status_code >= 500:
            r.raise_for_status()

        j = r.json()
        if 'errorCode' in j:
            if j['errorCode'] == 'errors.com.epicgames.oauth.corrective_action_required':
                self.log.error(f'{j["errorMessage"]} ({j["correctiveAction"]}), '
                               f'open the following URL to take action: {j["continuationUrl"]}')
            else:
                self.log.error(f'Login to EGS API failed with errorCode: {j["errorCode"]}')
            raise InvalidCredentialsError(j['errorCode'])
        elif r.status_code >= 400:
            self.log.error(f'EGS API responded with status {r.status_code} but no error in response: {j}')
            raise InvalidCredentialsError('Unknown error')

        self.session.headers['Authorization'] = f'bearer {j["access_token"]}'
        # only set user info when using non-anonymous login
        if not client_credentials:
            self.user = j

        return j

    def invalidate_session(self):  # unused
        _ = self.session.delete(f'https://{self._oauth_host}/account/api/oauth/sessions/kill/{self.access_token}',
                                timeout=self.request_timeout)

    def get_game_token(self):
        r = self.session.get(f'https://{self._oauth_host}/account/api/oauth/exchange',
                             timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def get_ownership_token(self, namespace, catalog_item_id):
        user_id = self.user.get('account_id')
        r = self.session.post(f'https://{self._ecommerce_host}/ecommerceintegration/api/public/'
                              f'platforms/EPIC/identities/{user_id}/ownershipToken',
                              data=dict(nsCatalogItemId=f'{namespace}:{catalog_item_id}'),
                              timeout=self.request_timeout)
        r.raise_for_status()
        return r.content

    def get_external_auths(self):
        user_id = self.user.get('account_id')
        r = self.session.get(f'https://{self._oauth_host}/account/api/public/account/{user_id}/externalAuths',
                             timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def get_game_assets(self, platform='Windows', label='Live'):
        r = self.session.get(f'https://{self._launcher_host}/launcher/api/public/assets/{platform}',
                             params=dict(label=label), timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def get_game_manifest(self, namespace, catalog_item_id, app_name, platform='Windows', label='Live'):
        r = self.session.get(f'https://{self._launcher_host}/launcher/api/public/assets/v2/platform'
                             f'/{platform}/namespace/{namespace}/catalogItem/{catalog_item_id}/app'
                             f'/{app_name}/label/{label}',
                             timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def get_launcher_manifests(self, platform='Windows', label=None):
        r = self.session.get(f'https://{self._launcher_host}/launcher/api/public/assets/v2/platform/'
                             f'{platform}/launcher', timeout=self.request_timeout,
                             params=dict(label=label if label else self._label))
        r.raise_for_status()
        return r.json()

    def get_user_entitlements(self):
        user_id = self.user.get('account_id')
        r = self.session.get(f'https://{self._entitlements_host}/entitlement/api/account/{user_id}/entitlements',
                             params=dict(start=0, count=5000), timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def get_game_info(self, namespace, catalog_item_id, timeout=None):
        r = self.session.get(f'https://{self._catalog_host}/catalog/api/shared/namespace/{namespace}/bulk/items',
                             params=dict(id=catalog_item_id, includeDLCDetails=True, includeMainGameDetails=True,
                                         country=self.country_code, locale=self.language_code),
                             timeout=timeout or self.request_timeout)
        r.raise_for_status()
        return r.json().get(catalog_item_id, None)

    def get_artifact_service_ticket(self, sandbox_id: str, artifact_id: str, label='Live', platform='Windows'):
        # Based on EOS Helper Windows service implementation. Only works with anonymous EOSH session.
        # sandbox_id is the same as the namespace, artifact_id is the same as the app name
        r = self.session.post(f'https://{self._artifact_service_host}/artifact-service/api/public/v1/dependency/'
                              f'sandbox/{sandbox_id}/artifact/{artifact_id}/ticket',
                              json=dict(label=label, expiresInSeconds=300, platform=platform),
                              params=dict(useSandboxAwareLabel='false'),
                              timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def get_game_manifest_by_ticket(self, artifact_id: str, signed_ticket: str, label='Live', platform='Windows'):
        # Based on EOS Helper Windows service implementation.
        r = self.session.post(f'https://{self._launcher_host}/launcher/api/public/assets/v2/'
                              f'by-ticket/app/{artifact_id}',
                              json=dict(platform=platform, label=label, signedTicket=signed_ticket),
                              timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def get_library_items(self, include_metadata=True):
        records = []
        r = self.session.get(f'https://{self._library_host}/library/api/public/items',
                             params=dict(includeMetadata=include_metadata),
                             timeout=self.request_timeout)
        r.raise_for_status()
        j = r.json()
        records.extend(j['records'])

        # Fetch remaining library entries as long as there is a cursor
        while cursor := j['responseMetadata'].get('nextCursor', None):
            r = self.session.get(f'https://{self._library_host}/library/api/public/items',
                                 params=dict(includeMetadata=include_metadata, cursor=cursor),
                                 timeout=self.request_timeout)
            r.raise_for_status()
            j = r.json()
            records.extend(j['records'])

        return records

    def get_user_cloud_saves(self, app_name='', manifests=False, filenames=None):
        if app_name:
            app_name += '/manifests/' if manifests else '/'

        user_id = self.user.get('account_id')

        if filenames:
            r = self.session.post(f'https://{self._datastorage_host}/api/v1/access/egstore/savesync/'
                                  f'{user_id}/{app_name}',
                                  json=dict(files=filenames),
                                  timeout=self.request_timeout)
        else:
            r = self.session.get(f'https://{self._datastorage_host}/api/v1/access/egstore/savesync/'
                                 f'{user_id}/{app_name}',
                                 timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def create_game_cloud_saves(self, app_name, filenames):
        return self.get_user_cloud_saves(app_name, filenames=filenames)

    def delete_game_cloud_save_file(self, path):
        url = f'https://{self._datastorage_host}/api/v1/data/egstore/{path}'
        r = self.session.delete(url, timeout=self.request_timeout)
        r.raise_for_status()

    def store_get_uplay_codes(self):
        user_id = self.user.get('account_id')
        r = self.session.post(f'https://{self._store_gql_host}/graphql',
                              headers={'user-agent': self._store_user_agent},
                              json=dict(query=uplay_codes_query,
                                        variables=dict(accountId=user_id)),
                              timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def store_claim_uplay_code(self, uplay_id, game_id):
        user_id = self.user.get('account_id')
        r = self.session.post(f'https://{self._store_gql_host}/graphql',
                              headers={'user-agent': self._store_user_agent},
                              json=dict(query=uplay_claim_query,
                                        variables=dict(accountId=user_id,
                                                       uplayAccountId=uplay_id,
                                                       gameId=game_id)),
                              timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()

    def store_redeem_uplay_codes(self, uplay_id):
        user_id = self.user.get('account_id')
        r = self.session.post(f'https://{self._store_gql_host}/graphql',
                              headers={'user-agent': self._store_user_agent},
                              json=dict(query=uplay_redeem_query,
                                        variables=dict(accountId=user_id,
                                                       uplayAccountId=uplay_id)),
                              timeout=self.request_timeout)
        r.raise_for_status()
        return r.json()
