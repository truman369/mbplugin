#!/usr/bin/python3
# -*- coding: utf8 -*-
import logging, os, sys, re, time, datetime, json, random
import store, settings
import browsercontroller

icon = '789C75524D4F5341143D84B6A8C0EB2BAD856A4B0BE5E301A508A9F8158DC18498A889896E8C3B638C31F147B83171E34E4388AE5C68E246A3C68D0B5DA82180B5B40A5A94B6F651DA423F012D2DE09D79CF4A207DC949A733F79C39F7CC1D3A37A801FF060912415451058772A09E6FFD04CD18F4DA09C267C214210051FB857EFFC1AFEEB3F3495E2F68DEA35EF396F086F6BCBC46D47E257C2304A1D7045157350DA13A80FA6A1F6AAB7CB4F6AB5A5E08DA71D2F840FC772AEF3B44DD0F1874215A87D1DA34871B57658CDE4F1212B87E2504BBD94F5A01D5938F7B16341F8937CB79C65DBF60DA2DC3E594F1FAE532D64B1BD8DCDCE428D1FAC5B30CDAAD33E483799C2E6B187411E245D124CC63BF18C3DD3BB9326F3B6EDF4A506FB3C49FE5BE99C6DE3D32F6E9636836C671A0631153DEB58AFCC9F155EA4DE951D40579CE8C6B37C5693F895347D388C9EB15F9D148119E1E190D3551F23DC7F366F73A2D4974DA52183E9E831CADCC0F878A38E88AC15C3B4F1A119E5D8B39814EEB125CAD199CF0E4C97FA9227F7CAC809E96382CE4D9489989BA9F7092EF2E7B8A7ACF62D0B58C278F8A15F90F4656D0D29880D5B0C07363EFD6665944B72385012947FC15DCBC56403EB7939BCD6CE0F2852CF193B0352C500F8C1F267EB2CC3FEC5EA10CFFE0D5F39D193C7D5C80BB2DCDEFDBCADFEEFF58FF2A2E9D2FC0F7E9BFC6C45809A74FE62035A778BDE23FCAFD3B28BF0EEB22E597E61E0EF52EE348DF2A2E9EFD8D87236B18BD57C099A13CE596E639B37AF6E66C5E597ECC0B7B7BA97909BDCE0CFA3BB3F074E73906A43CFADA73FC6DBAD4BB597D63DD3C0C35CA0C59049A3D933203926D89DFE3261D779B0217FD67DA2C273667AC9ECDBB323F33F80B823D9864'

login_url = 'https://login.mts.ru/amserver/UI/Login'  # - другая форма логина - там оба поля на одной странице, и можно запомнить сессию
# login_url = 'https://lk.mts.ru/'  # а на этой запомнить сессию нельзя
user_selectors = {
    # Возможно 2 разных формы логина, кроме того при заходе через мобильный МТС форма будет отличаться поэтому в выражении предусмотрены все варианты
    'chk_lk_page_js': "['form input[id=phoneInput]','form input[id=password]','form button[value=Ignore]','enter-with-phone-form'].filter(el => document.querySelector(el)!=null).length==0",
    'lk_page_url': 'login/userInfo', # не считаем что зашли в ЛК пока не прогрузим этот url
    # У нас форма из двух последовательных окон (хотя иногда бывает и одно, у МТС две разных формы логона)
    'chk_login_page_js': "['form input[id=phoneInput]','form input[id=password]','form button[value=Ignore]','enter-with-phone-form'].filter(el => document.querySelector(el)!=null).length>0",
    # Если мы зашли с интернета МТС то предлагается вариант зайти под номером владельца (есть два варианта этой формы), надо нажать кнопку проигнорить этот вариант
    'before_login_js': """b1=document.querySelector('button[value=Ignore]');
                          if(b1!==null){b1.click()};
                          b2=document.getElementById('enter-with-phone-form');
                          i2=document.getElementById('IDButton');
                          if(b2!==null && i2!==null){i2.value='Ignore';b2.submit.click();}
                        """,
    'login_clear_js': "document.querySelector('form input[id=phoneInput]').value=''",
    'login_selector': 'form input[id=phoneInput]',
    # проверка нужен ли submit после логина (если поле пароля уже есть то не нужен, иначе нужен)
    'chk_submit_after_login_js': "document.querySelector('form input[id=phoneInput]')!=null || document.querySelector('form input[id=password]')==null",
    'submit_after_login_js': "document.querySelectorAll('form [type=submit]').forEach(el => el.click())", # js для нажатия на далее после логона
    'submit_js': "document.querySelectorAll('form [type=submit]').forEach(el => el.click())",  # js для нажатия на финальный submit
    'remember_checker': "document.querySelector('form input[name=rememberme]')!=null && document.querySelector('form input[name=rememberme]').checked==false",  # Проверка что флаг remember me не выставлен
    'remember_js': "document.querySelector('form input[name=rememberme]').click()",  # js для выставления remember me
    'captcha_checker': "document.querySelector('img[id=captchaImage]')!=null||document.querySelector('div[id=captcha-wrapper]')!=null||document.body.innerText.startsWith('This question is for testing whether you are a human visitor and to prevent automated spam submission.')",
    'captcha_focus': "[document.getElementById('ans'),document.getElementById('password'),document.getElementById('captchaInput')].filter(s => s!=null).map(s=>s.focus())",
    'fatal': "/Доступ к сайту login.mts.ru запрещен./.test(document.querySelector('.descr').innerText)"
    }

class browserengine(browsercontroller.BrowserController):
    def data_collector(self):
        mts_usedbyme = self.options('mts_usedbyme')
        self.do_logon(url=login_url, user_selectors=user_selectors)

        # TODO close banner # document.querySelectorAll('div[class=popup__close]').forEach(s=>s.click())
        if self.login_ori != self.login and self.acc_num.isdigit():  # это финт для захода через другой номер
            # если заход через другой номер то переключаемся на нужный номер
            # TODO возможно с прошлого раза может сохраниться переключенный но вроде работает и так
            self.page_wait_for(selector="[id=ng-header__account-phone_desktop]")
            self.responses = {}  # Сбрасываем все загруженные данные - там данные по материнскому телефону
            # Так больше не работает
            # url_redirect = f'https://login.mts.ru/amserver/UI/Login?service=idp2idp&IDButton=switch&IDToken1=id={self.acc_num},ou=user,o=users,ou=services,dc=amroot&org=/users&ForceAuth=true&goto=https://lk.mts.ru'
            # Так тоже больше не работает
            # url_redirect = self.page_evaluate(f"Array.from(document.querySelectorAll('a.user-block__content')).filter(el => el.querySelector('.user-block__phone').innerText.replace(/\D/g,'').endsWith('{self.acc_num}'))[0].href")
            # self.page_goto(url_redirect)
            # Теперь сразу кликаем на нужный блок, если и это сломают - будем кликать playwright
            self.page_evaluate(f"Array.from(document.querySelectorAll('a.user-block__content')).filter(el => el.querySelector('.user-block__phone').innerText.replace(/\D/g,'').endsWith('{self.acc_num}'))[0].click()")
            # !!! Раньше я на каждой странице при таком заходе проверял что номер тот, сейчас проверяю только на старте
            for _ in range(10):
                self.sleep(1)
                numb = self.page_evaluate("document.getElementById('ng-header__account-phone_desktop').innerText")
                if numb is not None and numb !='':
                    break
            else:
                return  # номера на странице так и нет - уходим
            logging.info(f'PHONE {numb}')
            if re.sub(r'(?:\+7|\D)', '', numb) != self.acc_num:
                return  # Если номер не наш - уходим

        # Для начала только баланс быстрым способом (может запаздывать)
        self.wait_params(params=[
            {'name': 'Balance', 'url_tag': ['api/login/userInfo'], 'jsformula': "parseFloat(data.userProfile.balance).toFixed(2)"},
            # Закрываем банеры (для эстетики)
            {'name': '#banner1', 'url_tag': ['api/login/userInfo'], 'jsformula': "document.querySelectorAll('mts-dialog div[class=popup__close]').forEach(s=>s.click())", 'wait':False},
            ])

        # Потом все остальное
        res1 = self.wait_params(params=[
            {'name': 'TarifPlan', 'url_tag': ['api/login/userInfo'], 'jsformula': "data.userProfile.tariff.replace('(МАСС) (SCP)','')"},
            {'name': 'UserName', 'url_tag': ['api/login/userInfo'], 'jsformula': "data.userProfile.displayName"},
            {'name': 'Balance', 'url_tag': ['for=api/accountInfo/mscpBalance'], 'jsformula': "parseFloat(data.data.amount).toFixed(2)"},
            {'name': 'Balance2', 'url_tag': ['for=api/cashback/account'], 'jsformula': "parseFloat(data.data.balance).toFixed(2)"},
            {'name': '#counters', 'url_tag': ['for=api/sharing/counters'], 'jsformula': "data.data.counters"},
            ])
        if '#counters' in res1 and type(res1['#counters']) == list and len(res1['#counters'])>0:
            counters = res1['#counters']
            # deadlineDate
            deadline_dates = set([i['deadlineDate'] for i in counters if 'deadlineDate' in i])
            if len(deadline_dates)>0:
                deadline_date = min(deadline_dates)
                delta = datetime.datetime.fromisoformat(deadline_date) - datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(seconds=10800)))
                self.result['TurnOff'] = delta.days
                self.result['TurnOffStr'] = deadline_date.split('T')[0]
            # Минуты
            calling = [i for i in counters if i['packageType'] == 'Calling']
            if calling != []:
                unit = {'Second': 60, 'Minute': 1}.get(calling[0]['unitType'], 1)
                nonused = [i['amount'] for i in calling[0] ['parts'] if i['partType'] == 'NonUsed']
                usedbyme = [i['amount'] for i in calling[0] ['parts'] if i['partType'] == 'UsedByMe']
                if nonused != []:
                    self.result['Min'] = int(nonused[0]/unit)
                if usedbyme != []:
                    self.result['SpendMin'] = int(usedbyme[0]/unit)
            # SMS
            messaging = [i for i in counters if i['packageType'] == 'Messaging']
            if messaging != []:
                nonused = [i['amount'] for i in messaging[0] ['parts'] if i['partType'] == 'NonUsed']
                usedbyme = [i['amount'] for i in messaging[0] ['parts'] if i['partType'] == 'UsedByMe']
                if (mts_usedbyme == '0' or self.login not in mts_usedbyme.split(',')) and nonused != []:
                    self.result['SMS'] = int(nonused[0])
                if (mts_usedbyme == '1' or self.login in mts_usedbyme.split(',')) and usedbyme != []:
                    self.result['SMS'] = int(usedbyme[0])
            # Интернет
            internet = [i for i in counters if i['packageType'] == 'Internet']
            if internet != []:
                unitMult = settings.UNIT.get(internet[0]['unitType'], 1)
                unitDiv = settings.UNIT.get(self.options('interUnit'), 1)
                nonused = [i['amount'] for i in internet[0] ['parts'] if i['partType'] == 'NonUsed']
                usedbyme = [i['amount'] for i in internet[0] ['parts'] if i['partType'] == 'UsedByMe']
                if (mts_usedbyme == '0' or self.login not in mts_usedbyme.split(',')) and nonused != []:
                    self.result['Internet'] = round(nonused[0]*unitMult/unitDiv, 2)
                if (mts_usedbyme == '1' or self.login in mts_usedbyme.split(',')) and usedbyme != []:
                    self.result['Internet'] = round(usedbyme[0]*unitMult/unitDiv, 2)

        self.page_goto('https://lk.mts.ru/uslugi/podklyuchennye')
        res2 = self.wait_params(params=[
            {
                'name': '#services', 'url_tag': ['for=api/services/list/active$'],
                'jsformula': "data.data.services.map(s=>[s.name,!!s.subscriptionFee.value?s.subscriptionFee.value*(s.subscriptionFee.unitOfMeasureRaw=='DAY'?30:1):0])"
            },
            {
                'name': 'BlockStatus', 'url_tag': ['for=api/services/list/active'],
                'jsformula': "data.data.accountBlockStatus == 'Unblocked' ? '' : data.data.accountBlockStatus"
            },
        ])
        try:
            services = sorted(res2['#services'], key=lambda i:(-i[1],i[0]))
            free = len([a for a,b in services if b==0 and (a,b)!=('Ежемесячная плата за тариф', 0)])
            paid = len([a for a,b in services if b!=0])
            paid_sum = round(sum([b for a,b in services if b!=0]),2)
            self.result['UslugiOn'] = f'{free}/{paid}({paid_sum})'
            self.result['UslugiList'] = '\n'.join([f'{a}\t{b}' for a, b in services])
        except Exception:
            logging.info(f'Ошибка при получении списка услуг {store.exception_text()}')

        # Идем и пытаемся взять инфу со страницы https://lk.mts.ru/obshchiy_paket
        # Но только если телефон в списке в поле mts_usedbyme или для всех телефонов если там 1
        if mts_usedbyme == '1' or self.login in mts_usedbyme.split(',') or self.acc_num.lower().startswith('common'):
            self.page_goto('https://lk.mts.ru/obshchiy_paket')
            # 24.08.2021 иногда возвращается легальная страница, но вместо информации там сообщение об ошибке - тогда перегружаем и повторяем
            for i in range(3):
                res3 = {}
                res3_alt = self.wait_params(params=[{'name': '#checktask', 'url_tag': ['for=api/sharing/counters', '/longtask/'], 'jsformula': "data"}])
                if 'Donor' in str(res3_alt) or 'Acceptor' in str(res3_alt):
                    break  # Новый вариант аккумуляторов
                # TODO отключить в будущем
                res3 = self.wait_params(params=[{'name': '#checktask', 'url_tag': ['for=api/Widgets/GetUserClaims', '/longtask/'], 'jsformula': "data.result"}])
                if 'claim_error' not in str(res3):
                    break # Старый вариант аккумуляторов (если он уже не срабатывает приходит пустой без ошибки)
                logging.info(f'mts_usedbyme: GetUserClaims вернул claim_error - reload')
                self.page_reload()
                self.sleep(5)
            else:
                logging.info(f'mts_usedbyme: GetUserClaims за три попытки так и не дал результат. Уходим')
                self.result = {'ErrorMsg': 'Страница общего пакета не возвращает данных (claim_error)'}
                return
            try:
                # Обработка по новому варианту страницы api/sharing/counters
                if res3_alt.get('#checktask',{}).get('data',{}).get('subscriberType','')=='Donor':
                    logging.info(f'mts_usedbyme: Donor')
                    for el in res3_alt.get('#checktask',{}).get('data',{}).get('counters',[]):  # data.counters. ...
                        if el.get('packageType', '') == 'Calling':
                            self.result['SpendMin'] = int((el.get('usedAmount', 0) - el.get('usedByAcceptors', 0)) / 60)
                        if el.get('packageType', '') == 'Messaging':
                            self.result['SMS'] = el.get('usedAmount', 0) - el.get('usedByAcceptors', 0)
                        if el.get('packageType', '') == 'Internet':
                            self.result['Internet'] = round((el.get('usedAmount', 0) - el.get('usedByAcceptors', 0)) / 1024 / 1024, 3)
                if res3_alt.get('#checktask',{}).get('data',{}).get('subscriberType','')=='Acceptor':
                    logging.info(f'mts_usedbyme: Acceptor')
                    for el in res3_alt.get('#checktask',{}).get('data',{}).get('counters',[]):  # data.counters. ...
                        if el.get('packageType', '') == 'Calling':
                            self.result['SpendMin'] = int(el.get('usedAmount', 0) / 60)
                        if el.get('packageType', '') == 'Messaging':
                            self.result['SMS'] = el.get('usedAmount', 0)
                        if el.get('packageType', '') == 'Internet':
                            self.result['Internet'] = round(el.get('usedAmount', 0) / 1024 / 1024, 3)
                # TODO отключить в будущем
                # Обработка по старому варианту страницы api/Widgets/GetUserClaims
                if 'RoleDonor' in str(res3):  # Просто ищем подстроку во всем json вдруг что-то изменится
                    logging.info(f'mts_usedbyme: RoleDonor')
                    res4 = self.wait_params(params=[{'name': '#donor', 'url_tag': ['for=api/Widgets/AvailableCountersDonor$', '/longtask/'], 'jsformula': "data.result"}])
                    # acceptorsTotalConsumption - иногда возвращается 0 приходится считать самим
                    # data = {i['counterViewUnit']:i['groupConsumption']-i['acceptorsTotalConsumption'] for i in res4['#donor']}
                    data = {i['counterViewUnit']:i['groupConsumption']-sum([j.get('consumption',0) for j in i.get('acceptorsConsumption',[])]) for i in res4['#donor']}
                if 'RoleAcceptor' in str(res3):
                    logging.info(f'mts_usedbyme: RoleAcceptor')
                    res4 = self.wait_params(params=[{'name': '#acceptor', 'url_tag': ['for=api/Widgets/AvailableCountersAcceptor', '/longtask/'], 'jsformula': "data.result.counters"}])
                    data = {i['counterViewUnit']:i['consumption'] for i in res4['#acceptor']}
                if 'RoleDonor' in str(res3) or 'RoleAcceptor' in str(res3):
                    logging.info(f'mts_usedbyme collect: data={data}')
                    if 'MINUTE' in data:
                        self.result['SpendMin'] = data["MINUTE"]
                    if 'ITEM' in data:
                        self.result['SMS'] = data["ITEM"]
                    if 'GBYTE' in data:
                        self.result['Internet'] = data["GBYTE"]
                # Спецверсия для общего пакета, работает только для Donor
                if self.acc_num.lower().startswith('common'):
                    # Обработка по новому варианту страницы api/sharing/counters
                    if res3_alt.get('#checktask',{}).get('data',{}).get('subscriberType','')=='Donor':
                        logging.info(f'mts_usedbyme: Common for donor')
                        for el in res3_alt.get('#checktask',{}).get('data',{}).get('counters',[]):  # data.counters. ...
                            if el.get('packageType', '') == 'Calling':
                                self.result['Min'] = int((el.get('totalAmount', 0) - el.get('usedAmount', 0)) / 60)  # осталось минут
                                self.result['SpendMin'] = int((el.get('usedAmount', 0)) / 60)  # Потрачено минут
                            if el.get('packageType', '') == 'Messaging':
                                if 'rest' in self.acc_num:  # common_rest - общие остатки
                                    self.result['SMS'] = el.get('totalAmount', 0) - el.get('usedAmount', 0)
                                else:                       # потрачено
                                    self.result['SMS'] = el.get('usedAmount', 0)
                            if el.get('packageType', '') == 'Internet':
                                if 'rest' in self.acc_num:  # common_rest - общие остатки
                                    self.result['Internet'] = round((el.get('totalAmount', 0) - el.get('usedAmount', 0)) / 1024 / 1024, 3)
                                else:                       # потрачено
                                    self.result['Internet'] = round(el.get('usedAmount', 0) / 1024 / 1024, 3)
                    # TODO отключить в будущем старый вариант
                    # Обработка по старому варианту страницы api/Widgets/GetUserClaims
                    elif 'RoleDonor' in str(res3):
                        # потребление и остаток
                        cdata_charge = {i['counterViewUnit']:i['groupConsumption'] for i in res4['#donor']}
                        сdata_rest = {i['counterViewUnit']:i['counterLimit']-i['groupConsumption'] for i in res4['#donor']}
                        self.result['Min'] = сdata_rest["MINUTE"]  # осталось минут
                        self.result['SpendMin'] = cdata_charge["MINUTE"]  # Потрачено минут
                        if 'rest' in self.acc_num:
                            self.result['SMS'] = сdata_rest["ITEM"]  # остатки по инету и SMS
                            self.result['Internet'] = сdata_rest["GBYTE"]
                        else:
                            self.result['SMS'] = cdata_charge["ITEM"]  # расход по инету и SMS
                            self.result['Internet'] = cdata_charge["GBYTE"]
                        logging.info(f'mts_usedbyme common collect: сdata_rest={сdata_rest} cdata_charge={cdata_charge}')
                    else:  #  Со страницы общего пакета не отдали данные, чистим все, иначе будут кривые графики. ТОЛЬКО для common
                        raise RuntimeError(f'Страница общего пакета не возвращает данных')
            except Exception:
                logging.info(f'Ошибка при получении obshchiy_paket {store.exception_text()}')
                if self.acc_num.lower().startswith('common'):
                    self.result = {'ErrorMsg': 'Страница общего пакета не возвращает данных'}


# задействуем https://github.com/svetlyak40wt/mobile-balance
def get_balance_api(login, password, storename, plugin_name=__name__, fast_api=False):
    'plugin_name нужен для корректного доставания параметров из phones.ini, т.к. можем придти сюда из другого плагина mts2, fast_api=True - balance only'

    def get_tokens(response):
        csrf_token = re.search(r'name="csrf.sign" value="(.*?)"', response.text)
        csrf_ts_token = re.search(r'name="csrf.ts" value="(.*?)"', response.text)
        if csrf_token is None:
            raise_msg = "CSRF token not found"
            logging.error(raise_msg)
            raise RuntimeError(raise_msg, response)
        return csrf_token.group(1), csrf_ts_token.group(1)

    def check_status_code(response, expected_code):
        result_code = response.status_code
        if result_code != expected_code:
            raise_msg = f'{response.request.method} to {response.url} resulted in {result_code} status code instead of {expected_code}'
            logging.error(raise_msg)
            raise RuntimeError(raise_msg, response)

    def do_login():
        url = "http://login.mts.ru/amserver/UI/Login"
        user_agent = store.options('user_agent', pkey=store.get_pkey(login, plugin_name=__name__))
        if user_agent.strip() == '':
            user_agent = settings.default_user_agent
        headers = {"User-Agent": user_agent,}
        session = store.Session(storename, headers = headers)
        response = session.get(url, headers=headers)
        check_status_code(response, 200)
        #1
        csrf_token, csrf_ts_token = get_tokens(response)
        headers["Referer"] = url
        response = session.post(url,
            data={"IDToken1": login, "IDButton": "Submit", "encoded": "false", "loginURL": "?service=default", "csrf.sign": csrf_token, "csrf.ts": csrf_ts_token,},
            headers=headers,
        )
        check_status_code(response, 200)
        csrf_token, csrf_ts_token = get_tokens(response)
        #2
        fonts = 'cursive;monospace;serif;sans-serif;default;Arial;Arial Black;Arial Narrow;Bookman Old Style;Bradley Hand ITC;Century;Century Gothic;Comic Sans MS;Courier;Courier New;Georgia;Impact;Lucida Console;Papyrus;Tahoma;Times;Times New Roman;Trebuchet MS;Verdana;'
        fonts_l = fonts.split(';')
        fonts = ';'.join(fonts_l[:random.randint(5, len(fonts_l))])
        id_token_2 = {
            'screen': {'screenWidth': 1920, 'screenHeight': 1080, 'screenColourDepth': 24},
            'platform': 'Win32',
            'language': 'ru',
            'timezone': {'timezone': -180},
            'plugins': {'installedPlugins': ''},
            'fonts': { 'installedFonts': fonts},
            'userAgent': user_agent,
            'appName': 'Netscape',
            'appCodeName': user_agent.split('/', 1)[0],
            'appVersion': user_agent.split('/', 1)[1],
            'buildID': '20220101000000',
            'oscpu': 'Windows NT 6.1; Win64; x64',
            'product': 'Gecko',
            'productSub': '20100101'
        }
        response = session.post(url,
            data={
                "IDToken2": json.dumps(id_token_2),
                "csrf.sign": csrf_token,
                "csrf.ts": csrf_ts_token,
            },
            headers=headers,
        )
        #3
        csrf_token, csrf_ts_token = get_tokens(response)
        response = session.post(url,
            data={"IDToken1": login, "IDToken2": password, "IDButton": "Check", "encoded": "false", "loginURL": "?service=default", "csrf.sign": csrf_token, "csrf.ts": csrf_ts_token, },
            headers=headers,
            allow_redirects=False,
        )
        check_status_code(response, 200)
        #4
        csrf_token, csrf_ts_token = get_tokens(response)
        response = session.post(url,
            data={"IDButton": "Login", "encoded": "false", "csrf.sign": csrf_token, "csrf.ts": csrf_ts_token, },
            headers=headers,
            allow_redirects=False,
        )
        check_status_code(response, 302)
        return session

    def get_api_json(api, longtask=False):
        '''у МТС некоторые операции делаются в два приема (longtask==True), сначала берется одноразовый токен,
        а затем с этим токеном выдается страничка, иногда если слишком быстро попросить ответ  вместо нужного json
        возвращает json {'loginStatus':'InProgress'}  '''
        url = f'https://lk.mts.ru/{api}'
        if api.startswith('amserver/api'):
            longtask = False
            url = f'https://login.mts.ru/{api}'
        if longtask:
            logging.info(url)
            response1 = session.get(url + '?overwriteCache=false')
            logging.info(f'{response1.status_code}')
            token = response1.json()
            url = f'https://lk.mts.ru/api/longtask/check/{token}?for={api}'
        for l in range(10):  # 10 попыток TODO вынести в settings
            if longtask or l > 0:  # для не longtask запросов на первой итерации не ждем
                logging.info(f'Wait longtask')
                time.sleep(2)
            logging.info(f'{url}')
            response2 = session.get(url)
            logging.info(f'{response2.status_code}')
            if response2.status_code >= 400:
                return {}  # Вернули ошибку, продолжать нет смысла
            if response2.status_code == 204:  #  No Content - wait
                continue
            if response2.status_code != 200:
                continue  # Надо чуть подождать (бывает что и 6 секунд можно прождать)
            if 'json' in response2.headers.get('content-type'):
                # если у json есть 'loginStatus'=='InProgress' уходим на дополнительный круг
                if response2.json().get('loginStatus', '') != 'InProgress':
                    return response2.json()  # результат есть выходим из цикла
            else:
                logging.info(f"Not json:{response2.headers.get('content-type')}")
                # ответ есть и это не json - выходим
                return {}
        else:
            logging.info(f'Limit retry for {url}')
        return {}

    def options(param):
        ''' Обертка вокруг store.options чтобы передать в нее пару (номер, плагин) для вытаскивания индивидуальных параметров'''
        pkey = store.get_pkey(login, plugin_name)
        return store.options(param, pkey=pkey)

    mts_usedbyme = options('mts_usedbyme')
    session = store.Session(storename)
    user_info = get_api_json('api/login/userInfo', longtask=False)
    # Залогинены - если нет логинимся
    if 'userProfile' not in user_info:
        logging.info('userInfo not return json try relogin')
        session.drop_and_create()
        session = do_login()
        user_info = get_api_json('api/login/userInfo', longtask=False)
    result = {}

    # p_response = session.get("https://login.mts.ru/amserver/api/profile")
    profile = get_api_json('amserver/api/profile', longtask=False)
    result['Balance'] = round(float(profile.get("mobile:balance", 0)), 2)
    result['TarifPlan'] = profile.get('mobile:tariff', '')
    result['UserName'] = profile.get('profile:name', '')
    if fast_api:
        session.save_session()
        return result

    try:
        aib = get_api_json('api/accountInfo/mscpBalance', longtask=True)
        sla = get_api_json('api/services/list/active', longtask=True)
        sc = get_api_json('api/sharing/counters', longtask=True)
        cb = get_api_json('api/cashback/account', longtask=True)

        if 'amount' in aib:
            result['Balance'] = round(float(aib.get('data',{}).get('amount',0)), 2)
        else:
            logging.info(f'не смогли взять баланс с api/accountInfo/mscpBalance')
        result['Balance2'] = cb.get('data',{}).get('balance', 0)
        # Услуги
        sla_services = sla.get('data',{}).get('services', [])
        # services = [(i['name'], i.get('subscriptionFee', {}).get('value', 0)) for i in sla_services]
        # [(i['name'], i.get('subscriptionFee', {}).get('value', 0)*settings.UNIT.get(i.get('subscriptionFee', {}).get('unitOfMeasureRaw', 0), 1)) for i in sla_services]
        services = []
        for el in sla_services:
            name = el['name']
            subscription_fee = el.get('subscriptionFee', {})
            fee = subscription_fee.get('value', 0)
            unit = settings.UNIT.get(subscription_fee.get('unitOfMeasureRaw', 0),1)
            services.append([name, fee*unit])
        free = len([a for a,b in services if b==0 and (a,b)!=('Ежемесячная плата за тариф', 0)])
        paid = len([a for a,b in services if b!=0])
        paid_sum = round(sum([b for a,b in services if b!=0]),2)
        services.sort(key=lambda i:(-i[1],i[0]))
        result['UslugiOn']=f'{free}/{paid}({paid_sum})'
        result['UslugiList']='\n'.join([f'{a}\t{b}' for a,b in services])
        # Counters
        sc_counters = sc.get('data',{}).get('counters', [])
        # Минуты
        calling = [i for i in sc_counters if i['packageType'] == 'Calling']
        if calling != []:
            unit = {'Second': 60, 'Minute': 1}.get(calling[0]['unitType'], 1)
            nonused = [i['amount'] for i in calling[0] ['parts'] if i['partType'] == 'NonUsed']
            usedbyme = [i['amount'] for i in calling[0] ['parts'] if i['partType'] == 'UsedByMe']
            if nonused != []:
                result['Min'] = int(nonused[0]/unit)
            if usedbyme != []:
                result['SpendMin'] = int(usedbyme[0]/unit)
        # SMS
        messaging = [i for i in sc_counters if i['packageType'] == 'Messaging']
        if messaging != []:
            nonused = [i['amount'] for i in messaging[0] ['parts'] if i['partType'] == 'NonUsed']
            usedbyme = [i['amount'] for i in messaging[0] ['parts'] if i['partType'] == 'UsedByMe']
            if (mts_usedbyme == '0' or login not in mts_usedbyme.split(',')) and nonused != []:
                result['SMS'] = int(nonused[0])
            if (mts_usedbyme == '1' or login in mts_usedbyme.split(',')) and usedbyme != []:
                result['SMS'] = int(usedbyme[0])
        # Интернет
        internet = [i for i in sc_counters if i['packageType'] == 'Internet']
        if internet != []:
            unitMult = settings.UNIT.get(internet[0]['unitType'], 1)
            unitDiv = settings.UNIT.get(options('interUnit'), 1)
            nonused = [i['amount'] for i in internet[0] ['parts'] if i['partType'] == 'NonUsed']
            usedbyme = [i['amount'] for i in internet[0] ['parts'] if i['partType'] == 'UsedByMe']
            if (mts_usedbyme == '0' or login not in mts_usedbyme.split(',')) and nonused != []:
                result['Internet'] = round(nonused[0]*unitMult/unitDiv, 2)
            if (mts_usedbyme == '1' or login in mts_usedbyme.split(',')) and usedbyme != []:
                result['Internet'] = round(usedbyme[0]*unitMult/unitDiv, 2)

    except Exception:
        exception_text = f'Ошибка при получении дополнительных данных {store.exception_text()}'
        logging.error(exception_text)

    session.save_session()
    return result


def get_balance(login, password, storename=None, **kwargs):
    ''' На вход логин и пароль, на выходе словарь с результатами
    есть три режима работы (задается параметром plugin_mode):
    WEB - работа через браузер, забираем все возможные параметры (по умолчанию)
    API - работа через API забираем все возможные параметры
    FASTAPI - работа через API забираем только баланс
    '''
    # т.к. для совместимости остался приходящий сюда плагин mts2 пришлось пойти на трюк
    plugin_name = kwargs.get('plugin_name', __name__)
    pkey=store.get_pkey(login, plugin_name=plugin_name)
    plugin_mode = store.options('plugin_mode', pkey=pkey).upper()
    # Поменять дефолт если будут проблемы с playwright != 'WEB':
    if plugin_mode in ('API', 'FASTAPI'):
        fast_api = (plugin_mode == 'FASTAPI')
        return get_balance_api(login, password, storename, plugin_name=plugin_name, fast_api=fast_api)
    else:
        be = browserengine(login, password, storename, plugin_name=plugin_name)
        if str(store.options('show_captcha', pkey=pkey)) == '1':
            # если включен показ браузера в случае капчи то отключаем headless chrome - в нем видимость браузера не вернуть
            be.launch_config['headless'] = False
        return be.main()


if __name__ == '__main__':
    print('This is module mts on browser (mts)')
