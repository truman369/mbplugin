#!/usr/bin/python3
# -*- coding: utf8 -*-
from typing import List, Dict
import base64, datetime, gc, glob, json, logging, os, pathlib, pprint, random, re, socket, sys, threading, time, subprocess
import psutil, requests, playwright
import browsercontroller, store, settings
# костыль для тех у кого нет пакета websocket
try:
    import websocket
except Exception:
    os.system(f'{sys.executable} -m pip install websocket-client==1.5.1 psutil==5.9.5')
    import websocket
if sys.platform == 'win32':
    import win32gui, win32process

icon = '789C75524D4F5341143D84B6A8C0EB2BAD856A4B0BE5E301A508A9F8158DC18498A889896E8C3B638C31F147B83171E34E4388AE5C68E246A3C68D0B5DA82180B5B40A5A94B6F651DA423F012D2DE09D79CF4A207DC949A733F79C39F7CC1D3A37A801FF060912415451058772A09E6FFD04CD18F4DA09C267C214210051FB857EFFC1AFEEB3F3495E2F68DEA35EF396F086F6BCBC46D47E257C2304A1D7045157350DA13A80FA6A1F6AAB7CB4F6AB5A5E08DA71D2F840FC772AEF3B44DD0F1874215A87D1DA34871B57658CDE4F1212B87E2504BBD94F5A01D5938F7B16341F8937CB79C65DBF60DA2DC3E594F1FAE532D64B1BD8DCDCE428D1FAC5B30CDAAD33E483799C2E6B187411E245D124CC63BF18C3DD3BB9326F3B6EDF4A506FB3C49FE5BE99C6DE3D32F6E9636836C671A0631153DEB58AFCC9F155EA4DE951D40579CE8C6B37C5693F895347D388C9EB15F9D148119E1E190D3551F23DC7F366F73A2D4974DA52183E9E831CADCC0F878A38E88AC15C3B4F1A119E5D8B39814EEB125CAD199CF0E4C97FA9227F7CAC809E96382CE4D9489989BA9F7092EF2E7B8A7ACF62D0B58C278F8A15F90F4656D0D29880D5B0C07363EFD6665944B72385012947FC15DCBC56403EB7939BCD6CE0F2852CF193B0352C500F8C1F267EB2CC3FEC5EA10CFFE0D5F39D193C7D5C80BB2DCDEFDBCADFEEFF58FF2A2E9D2FC0F7E9BFC6C45809A74FE62035A778BDE23FCAFD3B28BF0EEB22E597E61E0EF52EE348DF2A2E9EFD8D87236B18BD57C099A13CE596E639B37AF6E66C5E597ECC0B7B7BA97909BDCE0CFA3BB3F074E73906A43CFADA73FC6DBAD4BB597D63DD3C0C35CA0C59049A3D933203926D89DFE3261D779B0217FD67DA2C273667AC9ECDBB323F33F80B823D9864'

# login_url 'https://login.mts.ru/amserver/UI/Login'  # - другая форма логина - там оба поля на одной странице, и можно запомнить сессию
login_url = 'https://lk.mts.ru/'  # а на этой запомнить сессию нельзя, но другой больше нет

def get_free_port() -> int:
    """Get free port."""
    sock = socket.socket()
    sock.bind(('localhost', 0))
    port = sock.getsockname()[1]
    sock.close()
    del sock
    gc.collect()
    return port


class PureBrowserDebug():

    def __init__(self, user_data_dir, response_store_path=None, headless_chrome=False, show_chrome=True, chrome_args=None) -> None:
        self.user_data_dir = user_data_dir  # chrome profile path
        self.response_store_path = response_store_path  # path for file log, screenshot store fith same name but png extension
        self.headless = headless_chrome  # for mts headles is broken headless_chrome always False
        self.show_chrome = show_chrome
        self.chrome_args = chrome_args if type(chrome_args) == list else []  # additional cmd argements for chrome
        self.port = get_free_port()  # port for CDP
        self._data: List[dict] = []  # store all winsocket reply
        self.chrome_hwnd: List[int] = []  # store chrome visible windows handle (windows only)
        self.responses: Dict[str, dict] = {}  # [f'{response.request.method}:{post} URL:{response.request.url}$'] = data
        self.ws_id = 0  # id counter for ws query
        self.fix_crash_banner()
        self.br_subp = self.run_chromium()  # run browser subprocess
        time.sleep(0.5)
        for n_nry in range(5):
            if self.br_subp.poll() is not None:  # chrome is not alive ?
                # browser not started kill all remote and exit
                try:
                    [p.kill() for p in psutil.process_iter() if p.name() == 'chrome.exe' and '--remote-debugging-port' in str(p.cmdline())]
                except Exception:
                    logging.info(f'kill old chrome: {store.exception_text()}')
                raise RuntimeError("Chromium did't start, kill all remote browsers")
            try:
                for i in range(50):  # wait while chrome started
                    self.chrome_proc = self.chrome_children()
                    if len(self.chrome_proc) > 3:
                        break
                    time.sleep(0.02)
                r1 = requests.get(f'http://localhost:{self.port}/json/list')
                logging.info(r1.json()[0])
                self.ws_url = [el.get('webSocketDebuggerUrl') for el in r1.json() if el.get('type') == 'page'][0]
                self.ws = websocket.WebSocket()
                self.ws.connect(self.ws_url)
                self.ws.settimeout(1)
                break
            except Exception:
                logging.info(store.exception_text())
                logging.info('Next try')
                time.sleep(1)
        else:
            raise RuntimeError("Chromium did't start after 5 retry")
        self.capture_screenshot(init=True)
        self.send("Network.enable")

    def fix_crash_banner(self):
        'Исправляем Preferences чтобы убрать баннер Работа Chrome была завершена некорректно'
        fn_pref = os.path.join(self.user_data_dir, 'Default', 'Preferences')
        if not os.path.exists(fn_pref):
            return  # Нет Preferences - выходим
        with open(fn_pref, encoding='utf8') as f:
            data = f.read()
        data1 = data.replace('"exit_type":"Crashed"', '"exit_type":"Normal"').replace('"exited_cleanly":false', '"exited_cleanly":true')
        if data != data1:
            logging.info(f'Fix chrome crash banner')
            open(fn_pref, encoding='utf8', mode='w').write(data1)

    def chrome_children(self):
        'get children and subchildren procs'
        try:
            children = psutil.Process().children() + sum([p.children() for p in psutil.Process().children()], [])
        except Exception:
            logging.error(f'chrome_children:v{store.exception_text()}')
            return []
        return [p for p in children if p.name() == 'chrome.exe']

    def run_chromium(self):
        try:
            browsers_json = json.load(open(os.path.join(os.path.split(playwright.__file__)[0], 'driver', 'package', 'browsers.json')))
            revision = [e for e in browsers_json['browsers'] if e['name'] == 'chromium'][0]['revision']
            if sys.platform == 'win32':
                pbp = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', os.path.join(os.environ.get('LOCALAPPDATA'), 'ms-playwright'))
                self.browser_path = os.path.join(pbp, f'chromium-{revision}', 'chrome-win', 'chrome.exe')
            elif sys.platform == 'linux':
                pbp = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', os.path.join(pathlib.Path.home(), '.cache', 'ms-playwright'))
                self.browser_path = os.path.join(pbp, f'chromium-{revision}', 'chrome-linux', 'chrome')
            elif sys.platform == 'darwin':
                pbp = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', os.path.join(pathlib.Path.home(), 'Library', 'Caches', 'ms-playwright'))
                self.browser_path = os.path.join(pbp, f'chromium-{revision}', 'chrome-mac', 'chrome')
            else:
                raise RuntimeError(f'Unknown platform {sys.platform} Chromium not found')
            if not os.path.exists(self.browser_path):
                raise RuntimeError(f'Chromium not found by path {self.browser_path}')
        except Exception:
            logging.error(store.exception_text())
            raise RuntimeError('Chromium not found')
        self.cmd = [self.browser_path, f'--user-data-dir={self.user_data_dir}', f'--remote-debugging-port={self.port}', '--enable-features=NetworkService,NetworkServiceInProcess', '--disable-save-password-bubble', '--no-default-browser-check', ' --disable-component-update', '--disable-extensions', '--disable-sync', '--no-first-run', '--no-service-autorun', f'--remote-allow-origins=http://localhost:{self.port}']
        self.cmd.extend(self.chrome_args)
        # ??? ' --headless --no-sandbox about:blank'
        logging.info(f'Browser start: {" ".join(self.cmd)}')
        proc = subprocess.Popen(self.cmd)
        return proc

    def get_visible_hwnd(self, pids):
        def enumWindowFunc(hwnd, windowList):
            """ win32gui.EnumWindows() callback """
            text = win32gui.GetWindowText(hwnd)
            className = win32gui.GetClassName(hwnd)
            tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            windowList.append((hwnd, text, className, tid, pid))
        if sys.platform != 'win32':
            return []
        try:
            myWindows = []
            win32gui.EnumWindows(enumWindowFunc, myWindows)
            # GWL_STYLE=-16 WS_VISIBLE = 268435456
            visible_hwnd = [wn[0] for wn in myWindows if wn[4] in pids and (win32gui.GetWindowLong(wn[0], -16) & 268435456)]
            return visible_hwnd
        except Exception:
            logging.error(f'While enumerate the window an exception occurred: {store.exception_text()}')

    def send(self, method, params=None):
        if params is None:
            params = {}
        self.ws_id += 1
        logging.info(f'send {self.ws_id}: {method} {params}')
        self.ws.send(json.dumps({"id": self.ws_id, "method": method, "params": params}))
        return self.ws_id

    def collect(self, id=None):
        id_countdown_timeout = 20  # FIXME make constant
        while True:
            # print(f'{len(self._data)}     ', end='\r')
            try:
                res = json.loads(self.ws.recv())
                self._data.append(res)
                if id is not None and res.get('id') == id:
                    if 'result' in res:
                        return res['result']
                    logging.info(res.get('error'))
                    return None
            except websocket.WebSocketTimeoutException:
                id_countdown_timeout -= 1
                if id is not None:
                    logging.info(f'Timeout for {id} (number {id_countdown_timeout}) was expired')
                if id is None or id_countdown_timeout < 0:
                    break
            except Exception:
                logging.info(store.exception_text())
                break
        return None

    def get(self, method, param):
        id = self.send(method, param)
        res = self.collect(id)
        return res

    def tget(self, js, chain):
        '''get by tree chain tget(js, 'params.request.url') -> js['params']['request']['url']'''
        res = js
        chain_list = chain.split('.')
        for el in chain_list[:-1]:
            res = res.get(el, {})
        return res.get(chain_list[-1], '')

    def browser_close(self):
        try:
            res = self.send('Browser.close')
            for i in range(50):
                if self.br_subp.poll() is not None:  # chrome finished ?
                    break
                time.sleep(0.1)
            else:
                self.br_subp.kill()
        except Exception:
            logging.info(store.exception_text())

    def __del__(self):
        if hasattr(self, 'br_subp') and self.br_subp.poll() is None:  # browser is running ?
            self.browser_close()

    def get_response_by_id(self, request_id):
        'wrapper for Network.getResponseBody + ws.recv for debug'
        id = self.send('Network.getResponseBody', {"requestId": request_id})
        res = self.collect(id)
        return res

    def get_response_body(self, url, partitial=True, ctype=''):
        'wrapper for Network.getResponseBody + ws.recv, add $ if need strongly end of url'
        self.collect()  # Прежде чем искать по response нужно собрать последние
        if partitial:
            request_id_list = [
                el['params']['requestId'] for el in self._data
                if url in (el.get('params', {}).get('response', {}).get('url', '') + '$')
                and ctype in el.get('params', {}).get('response', {}).get('headers', {}).get('Content-Type', '')
                and el.get('params', {}).get('response', {}).get('status', 0) not in [204, 400, 404]
            ]
        else:
            request_id_list = [el['params']['requestId'] for el in self._data if el.get('params', {}).get('response', {}).get('url', '') == url]
        if len(request_id_list) == 0:
            logging.info(f'Url {url} with {ctype=} not found in data')
            return None
        id = self.send('Network.getResponseBody', {"requestId": request_id_list[-1]})
        res = self.collect(id)
        if res is None:
            return ''
        if res.get('base64Encoded', True):
            return base64.b64decode(res.get('body', ''))
        else:
            return res.get('body', '')
        
    def len_data(self):
        return len(self._data)

    def get_response_body_json(self, url, partitial=True):
        'get_response_body + json.dumps if the result is not json retry every second until the timeout expiries'
        try:
            res = json.loads(self.get_response_body(url, partitial=partitial, ctype='json'))
            key = f'{url}_{len(self.responses)}'
            self.responses[key] = res
            try:
                if self.response_store_path is not None:
                    text = '\n\n'.join([f'{k}\n{pprint.PrettyPrinter(indent=4, width=160).pformat(v)}' for k, v in self.responses.items()])
                    open(self.response_store_path, 'w', encoding='utf8', errors='ignore').write(text)
            except Exception:
                logging.info(f'json decode error')
            return res
        except Exception:  # json.decoder.JSONDecodeError:
            logging.info(f'json decode error')
            return {}

    def jsformula(self, url, formula):
        'get json from url and evaluate as data'
        response_result = self.get_response_body_json(url)
        return self.page_eval(f"(()=>{{data={json.dumps(response_result,ensure_ascii=False)};return {formula};}})()")

    def capture_screenshot(self, filename=None, init=False, comment=''):
        'use filename or _1, _2, .... init=True - only delete old screenshot'
        if filename is None and self.response_store_path is None:
            return
        if filename is None:
            preffix = os.path.splitext(self.response_store_path)[0]
            mask = f'{preffix}*.png'
            num = len(glob.glob(mask)) + 1
            if len(comment) > 0:
                comment = '_' + comment
            filename = f'{preffix}_{num}{comment}.png'
            if init:
                for fn in glob.glob(mask):
                    os.remove(fn)
                return
        try:
            res = self.get('Page.captureScreenshot', {'format': 'png', 'quality': 80, 'fromSurface': True})
            if res is None:
                logging.info('Screenshot is None')
                return
            open(filename, 'wb').write(base64.b64decode(res['data']))
            logging.info(f'Screenshot {filename}')
        except Exception:
            logging.info(store.exception_text())

    def press_key(self, key):
        # do i need this ???  self.send('Runtime.evaluate', {'expression':'document.evaluate("//*[@id=\'login\']",document,null,XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,null).snapshotItem(0).focus()'})
        res = self.get('Input.dispatchKeyEvent', {'type': 'char', 'text': key})
        return res

    def check_selector(self, selector):
        'Checks for the presence of a selector on the page'
        res = self.get('Runtime.evaluate', {'expression': f"document.querySelector('{selector}')"})
        if type(res) is dict:
            return 'objectId' in res['result']
        else:
            return False

    def wait_selector(self, selector, timeout=30):
        'Waits for the selector to appear on the page'
        for i in range(timeout):
            self.check_selector(selector)
        else:
            logging.info(f'The waiting time has expired for {selector}')

    def page_fill(self, selector, text, delay=0.1):
        'enter text'
        # 'form input[type=tel]'
        res_1 = self.get('Runtime.evaluate', {'expression': f"document.querySelector('{selector}').focus()"})
        if 'exceptionDetails' in res_1:
            return
        res_2 = self.get('Runtime.evaluate', {'expression': f"document.querySelector('{selector}').value=''"})
        for ch in text:
            time.sleep(delay * random.random())
            res_ch = self.get('Input.dispatchKeyEvent', {'type': 'char', 'text': ch})
        return True

    def page_click(self, selector):
        self.get('Runtime.evaluate', {'expression': f"document.querySelectorAll('{selector}').forEach(el => el.click())"})

    def page_eval_ext(self, expression):
        # 'document.title'  'document.location.href'
        res = self.get('Runtime.evaluate', {'expression': expression})
        return res

    def page_eval(self, expression):
        # 'document.title'  'document.location.href'
        res = self.get('Runtime.evaluate', {'expression': expression}).get('result', {}).get('value', '')
        return res


def get_balance(login, password, storename=None, wait=True, **kwargs):
    ''' На вход логин и пароль, на выходе словарь с результатами '''

    def options(param):
        ''' Обертка вокруг store.options чтобы передать в нее пару (номер, плагин) для вытаскивания индивидуальных параметров'''
        pkey = store.get_pkey(login, plugin_name)
        return store.options(param, pkey=pkey)

    def wait_state(timeout=30):
        'Состояние в котором находимся'
        state = 'unknown'
        time.sleep(1)
        for i in range(timeout):
            location = pd.page_eval('window.location.toString()')
            logging.info(f'{location=} collect {pd.len_data()}')
            if pd.check_selector('.footer .guru'):
                state = 'qrator'
            elif pd.check_selector('form input[type=tel]'):
                state = 'login'
            elif pd.check_selector('div[data-test-id=verify-otp]'):
                state = 'sms'
            elif pd.check_selector('form input[id=password]'):
                state = 'password'
            elif pd.check_selector('mts-lk-root'):
                state = 'lk'
            else:
                time.sleep(1)
                continue
            logging.info(f'state={state}')
            break
        else:
            logging.error('Не дождались никакого известного состояния')
        return state

    plugin_name = __name__
    login_ori, acc_num = login, ''
    if '/' in login:
        login, acc_num = login_ori.split('/')
    mts_usedbyme = options('mts_usedbyme')
    store.turn_logging()
    session = store.Session(storename)
    logging.info(f"Start {kwargs=}")
    storefolder = options('storefolder')
    user_data_dir = store.abspath_join(storefolder, 'headless', f'p_{__name__}_{login}')
    response_store_path = None
    if storename is not None:
        response_store_path = store.abspath_join(options('loggingfolder'), storename + '.log')
    headless_chrome = (str(options('headless_chrome')) == '1') and (str(options('show_chrome')) == '0')  # headless if headless and NOT show_chrome
    show_chrome = str(options('show_chrome')) == '1'
    result = {}
    headless_chrome = False  # FIX !!! МТС в headless не работает
    show_chrome = True  # FIX !!! МТС без show_chrome не работает
    chrome_args = []
    if options('browser_proxy').strip() != '':
        chrome_args.append(f'--proxy-server={options("browser_proxy").strip()}')
    pd = PureBrowserDebug(user_data_dir, response_store_path, headless_chrome=headless_chrome, show_chrome=show_chrome, chrome_args=chrome_args)
    # 1 Is login ???
    store.feedback.text(f"Run browser", append=True)
    pd.send('Page.navigate', {'url': login_url})
    state = wait_state()
    if state == 'unknown':
        pd.capture_screenshot()
        pd.send('Page.navigate', {'url': login_url})
        state = wait_state()
    pd.capture_screenshot()

    if state == 'qrator':
        store.feedback.text(f"Qrator", append=True)
        logging.error('Сработала защита, попробуйте запустить в режиме show_chrome=0')
        return

    login_pause = int(options('login_pause'))
    if state != 'lk' and login_pause > 0:
        logging.info(f'Login pause {login_pause}')
        for i in range(login_pause):
            if wait_state(1) == 'lk':
                break

    state = wait_state()
    if state == 'login':
        store.feedback.text(f"Login", append=True)
        pd.page_fill('form input[type=tel]', login)
        pd.page_click('form [type=submit]')
        state = wait_state()
        pd.capture_screenshot()

    state = wait_state()
    if state == 'password':
        store.feedback.text(f"Password", append=True)
        pd.page_fill('form input[id=password]', password)
        pd.page_click('form [type=submit]')
        state = wait_state()
        pd.capture_screenshot()

    state = wait_state()
    if state == 'lk':
        store.feedback.text(f"User info", append=True)
        user_info = pd.get_response_body_json('api/login/user-info')
        user_profile = user_info.get('userProfile', {})
        # rich.print(ui)
        # parseFloat(data.userProfile.balance).toFixed(2)
        if 'balance' in user_profile:
            result['Balance'] = round(user_profile['balance'], 2)
        # Закрываем банеры (для эстетики)
        pd.page_eval("document.querySelectorAll('mts-dialog div[class=popup__close]').forEach(s=>s.click())==null")
        # Потом все остальное
        result['TarifPlan'] = user_profile.get('tariff', '').replace('(МАСС) (SCP)', '')
        result['UserName'] = user_profile.get('displayName', '')
        # ждем longtask тормозную страницу
        logging.info(f'Wait mscpBalance and counters')
        for cnt in range(30):
            if pd.get_response_body('for=api/accountInfo/mscpBalance') != '' and pd.get_response_body('for=api/sharing/counters') != '':
                break
            time.sleep(1)
        pd.capture_screenshot()
        mccsp_balance = pd.get_response_body_json('for=api/accountInfo/mscpBalance')
        # amount брать нельзя т.к. он здесь криво округленный под показ на странице
        # но если баланс нулевой а amount не нулевой то нам вернули кривой баланс и мы его выкидываем
        if 'amount' in mccsp_balance and 'Balance' in result:
            if mccsp_balance['amount'] > 0 and result['Balance'] == 0:
                del result['Balance']
        cashback_page = pd.get_response_body_json('for=api/cashback/account')
        # pd.jsformula('for=api/cashback/account', "parseFloat(data.data.balance).toFixed(2)")
        cashback_data = cashback_page.get('data', {})
        if 'balance' in cashback_data:
            result['Balance2'] = round(cashback_data['balance'], 2)
        counters = pd.get_response_body_json('for=api/sharing/counters').get('data', {}).get('counters', [])
        if 'Balance' in result and 'Balance2' in result:
            try:
                result['Balance3'] = float(result['Balance']) + float(result['Balance2'])
            except Exception:
                logging.info(f'Не смогли сложить балансы {store.exception_text()}')
        if type(counters) == list and len(counters) > 0:
            # deadlineDate
            deadline_dates = set([i['deadlineDate'] for i in counters if 'deadlineDate' in i])
            if len(deadline_dates) > 0:
                deadline_date = min(deadline_dates)
                delta = datetime.datetime.fromisoformat(deadline_date) - datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(seconds=10800)))
                result['TurnOff'] = delta.days
                result['TurnOffStr'] = deadline_date.split('T')[0]
            # Минуты
            calling = [i for i in counters if i['packageType'] == 'Calling']
            if calling != []:
                unit = {'Second': 60, 'Minute': 1}.get(calling[0]['unitType'], 1)
                nonused = [i['amount'] for i in calling[0]['parts'] if i['partType'] == 'NonUsed']
                usedbyme = [i['amount'] for i in calling[0]['parts'] if i['partType'] == 'UsedByMe']
                if nonused != []:
                    result['Min'] = int(nonused[0] / unit)
                if usedbyme != []:
                    result['SpendMin'] = int(usedbyme[0] / unit)
            # SMS
            messaging = [i for i in counters if i['packageType'] == 'Messaging']
            if messaging != []:
                nonused = [i['amount'] for i in messaging[0]['parts'] if i['partType'] == 'NonUsed']
                usedbyme = [i['amount'] for i in messaging[0]['parts'] if i['partType'] == 'UsedByMe']
                if (mts_usedbyme == '0' or login not in mts_usedbyme.split(',')) and nonused != []:
                    result['SMS'] = int(nonused[0])
                if (mts_usedbyme == '1' or login in mts_usedbyme.split(',')) and usedbyme != []:
                    result['SMS'] = int(usedbyme[0])
            # Интернет
            internet = ([i for i in counters if i['packageType'] == 'Internet' and i.get('packageGroup') == 'Main'] +
                        [i for i in counters if i['packageType'] == 'Internet' and i.get('packageGroup') != 'Main'])
            # by https://github.com/artyl/mbplugin/issues/39
            internet.sort(key=lambda el: (el.get('packageGroup') == 'Main', el.get('priority', 0)), reverse=True)
            if internet != []:
                unitMult = settings.UNIT.get(internet[0]['unitType'], 1)
                unitDiv = settings.UNIT.get(options('interUnit'), 1)
                nonused = [i['amount'] for i in internet[0]['parts'] if i['partType'] == 'NonUsed']
                usedbyme = [i['amount'] for i in internet[0]['parts'] if i['partType'] == 'UsedByMe']
                if (mts_usedbyme == '0' or login not in mts_usedbyme.split(',')) and nonused != []:
                    result['Internet'] = round(nonused[0] * unitMult / unitDiv, 2)
                if (mts_usedbyme == '1' or login in mts_usedbyme.split(',')) and usedbyme != []:
                    result['Internet'] = round(usedbyme[0] * unitMult / unitDiv, 2)

        store.feedback.text(f"Uslugi", append=True)
        pd.send('Page.navigate', {'url': 'https://lk.mts.ru/uslugi/podklyuchennye'})
        # ждем longtask тормозную страницу
        for cnt in range(30):
            if pd.get_response_body('for=api/services/list/active$') != '':
                break
            time.sleep(1)
        pd.capture_screenshot()
        # services = pd.jsformula('for=api/services/list/active$', "data.data.services.map(s=>[s.name,!!s.subscriptionFee.value?s.subscriptionFee.value*(s.subscriptionFee.unitOfMeasureRaw=='DAY'?30:1):0])")
        active = pd.get_response_body_json('for=api/services/list/active$')
        # (name, cost, period)
        services_ = [(e.get('name', ''), e.get('subscriptionFee', {}).get('value', 0), e.get('subscriptionFee', {}).get('unitOfMeasureRaw', ''))
                     for e in active.get('data', {}).get('services', [])]
        services_2 = [(s, c * (30 if p == 'DAY' else 1)) for s, c, p in services_]
        result['BlockStatus'] = active.get('data', {}).get('accountBlockStatus', '').replace('Unblocked', '')
        try:
            services = sorted(services_2, key=lambda i: (-i[1], i[0]))
            free = len([a for a, b in services if b == 0 and (a, b) != ('Ежемесячная плата за тариф', 0)])
            paid = len([a for a, b in services if b != 0])
            paid_sum = round(sum([b for a, b in services if b != 0]), 2)
            result['UslugiOn'] = f'{free}/{paid}({paid_sum})'
            result['UslugiList'] = '\n'.join([f'{a}\t{b}' for a, b in services]).replace('&nbsp;', ' ')
        except Exception:
            logging.info(f'Ошибка при получении списка услуг {store.exception_text()}')

        # Идем и пытаемся взять инфу со страницы https://lk.mts.ru/obshchiy_paket
        # Теперь это на https://lk.ssl.mts.ru/sharing
        # Но только если телефон в списке в поле mts_usedbyme или для всех телефонов если там 1
        if mts_usedbyme == '1' or login in mts_usedbyme.split(',') or acc_num.lower().startswith('common'):
            # 24.08.2021 иногда возвращается легальная страница, но вместо информации там сообщение об ошибке - тогда перегружаем и повторяем
            store.feedback.text(f"Sharing", append=True)
            pd.send('Page.navigate', {'url': 'https://lk.mts.ru/sharing'})
            for cnt in range(30):
                if pd.get_response_body('for=api/sharing/counters') != '':
                    break
                time.sleep(1)
            pd.capture_screenshot()
            res3_alt = pd.get_response_body_json('for=api/sharing/counters').get('data', {})
            # Пока просто исключаем Tethering, потом посмотрим как быть если варианты появяться
            counters = [el for el in res3_alt.get('counters', []) if el.get('packageGroup', '') not in ['Tethering']]
            try:
                # Обработка по новому варианту страницы api/sharing/counters
                if res3_alt.get('subscriberType', '') == 'Donor':
                    logging.info(f'mts_usedbyme: Donor')
                    for el in counters:  # data.counters. ...
                        if el.get('packageType', '') == 'Calling':
                            result['SpendMin'] = int((el.get('usedAmount', 0) - el.get('usedByAcceptors', 0)) / 60)
                        if el.get('packageType', '') == 'Messaging':
                            result['SMS'] = el.get('usedAmount', 0) - el.get('usedByAcceptors', 0)
                        if el.get('packageType', '') == 'Internet':
                            result['Internet'] = round((el.get('usedAmount', 0) - el.get('usedByAcceptors', 0)) / 1024 / 1024, 3)
                if res3_alt.get('subscriberType', '') == 'Acceptor':
                    logging.info(f'mts_usedbyme: Acceptor')
                    for el in counters:  # data.counters. ...
                        if el.get('packageType', '') == 'Calling':
                            result['SpendMin'] = int(el.get('usedAmount', 0) / 60)
                        if el.get('packageType', '') == 'Messaging':
                            result['SMS'] = el.get('usedAmount', 0)
                        if el.get('packageType', '') == 'Internet':
                            result['Internet'] = round(el.get('usedAmount', 0) / 1024 / 1024, 3)
                # Спецверсия для общего пакета, работает только для Donor
                if acc_num.lower().startswith('common'):
                    # Обработка по новому варианту страницы api/sharing/counters
                    if res3_alt.get('subscriberType', '') == 'Donor':
                        logging.info(f'mts_usedbyme: Common for donor')
                        for el in counters:  # data.counters. ...
                            if el.get('packageType', '') == 'Calling':
                                result['Min'] = int((el.get('totalAmount', 0) - el.get('usedAmount', 0)) / 60)  # осталось минут
                                result['SpendMin'] = int((el.get('usedAmount', 0)) / 60)  # Потрачено минут
                            if el.get('packageType', '') == 'Messaging':
                                if 'rest' in acc_num:  # common_rest - общие остатки
                                    result['SMS'] = el.get('totalAmount', 0) - el.get('usedAmount', 0)
                                else:                       # потрачено
                                    result['SMS'] = el.get('usedAmount', 0)
                            if el.get('packageType', '') == 'Internet':
                                if 'rest' in acc_num:  # common_rest - общие остатки
                                    result['Internet'] = round((el.get('totalAmount', 0) - el.get('usedAmount', 0)) / 1024 / 1024, 3)
                                else:                       # потрачено
                                    result['Internet'] = round(el.get('usedAmount', 0) / 1024 / 1024, 3)
                    else:  # Со страницы общего пакета не отдали данные, чистим все, иначе будут кривые графики. ТОЛЬКО для common
                        raise RuntimeError(f'Страница общего пакета не возвращает данных')
            except Exception:
                logging.info(f'Ошибка при получении obshchiy_paket {store.exception_text()}')
                if acc_num.lower().startswith('common'):
                    result = {'ErrorMsg': 'Страница общего пакета не возвращает данных'}
    pd.capture_screenshot()
    store.feedback.text(f"Done", append=True)
    pd.browser_close()
    return result

if __name__ == '__main__':
    print('This is module mts on browser (mts)')
