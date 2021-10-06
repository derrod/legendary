import logging
import json
import webbrowser

logger = logging.getLogger('WebViewHelper')
webview_available = True

try:
    import webview

    # silence logger
    webview.logger.setLevel(logging.FATAL)
    webview.initialize()
except Exception as e:
    logger.debug(f'Webview unavailable, disabling webview login (Exception: {e!r}).')
    webview_available = False

login_url = 'https://www.epicgames.com/id/login'
sid_url = 'https://www.epicgames.com/id/api/redirect?'
logout_url = 'https://www.epicgames.com/id/logout?productName=epic-games&redirectUrl=https://www.epicgames.com/site/'
window_js = '''
window.ue = {
    signinprompt: {
        requestexchangecodesignin: pywebview.api.set_exchange_code,
        registersignincompletecallback: pywebview.api.trigger_sid_exchange
    },
    common: {
        launchexternalurl: pywebview.api.open_url_external,
        // not required, just needs to be non-null
        auth: {
            completeLogin: pywebview.api.nop
        }
    }
}
'''

get_sid_js = '''
function on_loaded() {
    pywebview.api.login_sid(this.responseText);
}

var sid_req = new XMLHttpRequest();
sid_req.addEventListener("load", on_loaded);
sid_req.open("GET", "/id/api/redirect?");
sid_req.send();
'''


class MockLauncher:
    def __init__(self, callback=None):
        self.callback = callback
        self.window = None
        self.exchange_code = None
        self.sid = None
        self.inject_js = True
        self.destroy_on_load = False
        self.callback_result = None

    def on_loaded(self):
        url = self.window.get_current_url()
        logger.debug(f'Loaded url: {url.partition("?")[0]}')
        # make sure JS necessary window. stuff is available
        if self.inject_js:
            self.window.evaluate_js(window_js)

        if 'logout' in url:
            # prepare to close browser after logout redirect
            self.destroy_on_load = True
        elif self.destroy_on_load:
            # close browser after logout
            logger.info('Closing web view...')
            self.window.destroy()

    def nop(self, *args, **kwargs):
        return

    def open_url_external(self, url):
        webbrowser.open(url)

    def set_exchange_code(self, exchange_code):
        logger.debug('Got exchange code (stage 1)!')
        # we cannot use this exchange code as our login would be invalidated
        # after logging out on the website. Hence we do the dance of using
        # the SID to create *another* exchange code which will create a session
        # that remains valid after logging out.
        self.exchange_code = exchange_code

    def trigger_sid_exchange(self, *args, **kwargs):
        self.inject_js = False
        # first obtain SID, then log out
        self.window.evaluate_js(get_sid_js)

    def login_sid(self, sid_json):
        try:
            j = json.loads(sid_json)
            self.sid = j['sid']
            logger.debug(f'Got SID (stage 2)!')
            if self.callback:
                logger.debug(f'Calling login callback...')
                self.callback_result = self.callback(self.sid)
        except Exception as e:
            logger.error(f'Loading SID response failed with {e!r}')
        finally:
            logger.debug('Starting browser logout...')
            self.window.load_url(logout_url)


def do_webview_login(callback=None):
    api = MockLauncher(callback=callback)
    logger.info('Opening web view with Epic Games Login...')
    window = webview.create_window('Epic Login', url=login_url, width=1024, height=1024, js_api=api)
    api.window = window
    window.loaded += api.on_loaded
    webview.start()

    return api.callback_result
