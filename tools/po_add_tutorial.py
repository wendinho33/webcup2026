"""Append first-login tutorial strings to each locale .po (no msgmerge bloat).

Run:
    python tools/po_add_tutorial.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from po_tool import PO_ROOT, quote  # noqa: E402

TRANSLATIONS = {
    'fr': {
        'First contact': 'Premier contact',
        'Welcome to Terra Nova': 'Bienvenue sur Terra Nova',
        'Skip tour': 'Passer la visite',
        'Your home base. Track your callsign, clearance, departure countdown and passenger record here.': "Votre base d'attache. Suivez ici votre indicatif, votre habilitation, le compte à rebours du départ et votre dossier passager.",
        'You start with a 10,000 TRX welcome bonus. Buy and sell TerraX in the market against Earth credits.': 'Vous démarrez avec un bonus de bienvenue de 10 000 TRX. Achetez et vendez des TerraX sur le marché contre des crédits terrestres.',
        'News & signals': 'Actualités & signaux',
        'Read the latest dispatches, leave comments, and watch the bell for notifications and security alerts.': 'Lisez les dernières dépêches, laissez des commentaires et surveillez la cloche pour les notifications et alertes de sécurité.',
        'Weather & alerts': 'Météo & alertes',
        "Live weather for the settlement. Turn on browser push to get storm warnings even when you're away.": 'Météo en direct de la colonie. Activez les notifications push du navigateur pour recevoir les alertes de tempête même en votre absence.',
        'City services': 'Services municipaux',
        'Transport timetables, health check-ups with Terra Watch, government tax and pension, and Terra Chat.': 'Horaires de transport, bilans de santé avec Terra Watch, impôts et pension du gouvernement, et Terra Chat.',
        'Feedback & help': 'Avis & aide',
        "Tell us what's broken or missing on the Feedback page. Adjust text size and contrast under accessibility.": 'Signalez ce qui ne fonctionne pas ou ce qui manque sur la page Avis. Réglez la taille du texte et le contraste dans Accessibilité.',
        'Back': 'Retour',
        'Next': 'Suivant',
        'Got it': 'Compris',
    },
    'mg': {
        'First contact': 'Fifandraisana voalohany',
        'Welcome to Terra Nova': 'Tonga soa eto Terra Nova',
        'Skip tour': 'Hitsidina',
        'Your home base. Track your callsign, clearance, departure countdown and passenger record here.': 'Ny toeram-ponenanao. Araho eto ny kaodim-piaranao, ny fahazoan-dàlanao, ny fanisam-potoana hialàna ary ny rakitsoratrao.',
        'You start with a 10,000 TRX welcome bonus. Buy and sell TerraX in the market against Earth credits.': "Manomboka amin'ny bonus fandraisana 10 000 TRX ianao. Mividiana sy amidio TerraX eny an-tsena amin'ny crédit an-tany.",
        'News & signals': 'Vaovao & famantarana',
        'Read the latest dispatches, leave comments, and watch the bell for notifications and security alerts.': 'Vakio ny tatitra farany, mametraha fanehoan-kevitra, ary araho ny lakolosy hahazoana fampandrenesana sy fanairana fiarovana.',
        'Weather & alerts': "Toetr'andro & fanairana",
        "Live weather for the settlement. Turn on browser push to get storm warnings even when you're away.": "Toetr'andro mivantana ho an'ny tanàna. Alefaso ny push an'ny navigateur mba hahazoana fanairana rivo-mahery na dia tsy eo aza ianao.",
        'City services': 'Serivisy an-tanàna',
        'Transport timetables, health check-ups with Terra Watch, government tax and pension, and Terra Chat.': "Fandaharam-potoanan'ny fitaterana, fizahana ara-pahasalamana amin'ny Terra Watch, hetra sy fisotroan-drononon'ny governemanta, ary Terra Chat.",
        'Feedback & help': 'Hevitra & fanampiana',
        "Tell us what's broken or missing on the Feedback page. Adjust text size and contrast under accessibility.": "Lazao izay simba na tsy ampy ao amin'ny pejin'ny hevitra. Ahitsio ny haben'ny soratra sy ny contraste ao amin'ny fidirana.",
        'Back': 'Miverina',
        'Next': 'Manaraka',
        'Got it': 'Azoko',
    },
    'mfe': {
        'First contact': 'Premie kontak',
        'Welcome to Terra Nova': 'Bienveni lor Terra Nova',
        'Skip tour': 'Sote vizit',
        'Your home base. Track your callsign, clearance, departure countdown and passenger record here.': 'To baz prinsipal. Swiv to sinyal, to clearance, konte-a-rebour depa ek to dosye pasaze isi.',
        'You start with a 10,000 TRX welcome bonus. Buy and sell TerraX in the market against Earth credits.': 'To koumans avek enn bonis bienveni 10 000 TRX. Aste ek vann TerraX lor marse kont kredi Later.',
        'News & signals': 'Nouvel & sinyal',
        'Read the latest dispatches, leave comments, and watch the bell for notifications and security alerts.': 'Lir bann dernie dispatch, les komanter, ek get sinyal lor laklos pou notifikasion ek alert sekirite.',
        'Weather & alerts': 'Metéo & alert',
        "Live weather for the settlement. Turn on browser push to get storm warnings even when you're away.": 'Meteo an direk pou koloni. Aktive push navigateur pou gagn bann alerte loraz mem si to pa la.',
        'City services': 'Servis vil',
        'Transport timetables, health check-ups with Terra Watch, government tax and pension, and Terra Chat.': 'Orer transport, check-up sante avek Terra Watch, taks ek pansyon gouvernman, ek Terra Chat.',
        'Feedback & help': 'Feedback & led',
        "Tell us what's broken or missing on the Feedback page. Adjust text size and contrast under accessibility.": 'Dir nou ki kase ou ki manke lor paz Feedback. Aziste taille text ek kontras dan aksesibilite.',
        'Back': 'Retourne',
        'Next': 'Swivan',
        'Got it': 'Konpran',
    },
    'zh': {
        'First contact': '首次接触',
        'Welcome to Terra Nova': '欢迎来到新地球（Terra Nova）',
        'Skip tour': '跳过导览',
        'Your home base. Track your callsign, clearance, departure countdown and passenger record here.': '您的主基地。在这里查看您的呼号、权限、出发倒计时和乘客档案。',
        'You start with a 10,000 TRX welcome bonus. Buy and sell TerraX in the market against Earth credits.': '您将以 10,000 TRX 欢迎奖励起步，可在市场用地球信用点买卖 TerraX。',
        'News & signals': '新闻与信号',
        'Read the latest dispatches, leave comments, and watch the bell for notifications and security alerts.': '阅读最新快讯、发表评论，并留意铃铛中的通知和安全警报。',
        'Weather & alerts': '天气与警报',
        "Live weather for the settlement. Turn on browser push to get storm warnings even when you're away.": '定居点的实时天气。开启浏览器推送，即使您不在也能收到风暴警告。',
        'City services': '城市服务',
        'Transport timetables, health check-ups with Terra Watch, government tax and pension, and Terra Chat.': '交通时刻表、Terra Watch 健康体检、政府税务与养老金，以及 Terra Chat。',
        'Feedback & help': '反馈与帮助',
        "Tell us what's broken or missing on the Feedback page. Adjust text size and contrast under accessibility.": '请在“反馈”页面告诉我们哪里有问题或缺失；可在“无障碍”中调整文字大小和对比度。',
        'Back': '返回',
        'Next': '下一步',
        'Got it': '知道了',
    },
    'ru': {
        'First contact': 'Первый контакт',
        'Welcome to Terra Nova': 'Добро пожаловать на Terra Nova',
        'Skip tour': 'Пропустить тур',
        'Your home base. Track your callsign, clearance, departure countdown and passenger record here.': 'Ваша база. Здесь отслеживайте позывной, уровень допуска, обратный отсчёт до отправления и личное дело.',
        'You start with a 10,000 TRX welcome bonus. Buy and sell TerraX in the market against Earth credits.': 'Вы начинаете с приветственного бонуса в 10 000 TRX. Покупайте и продавайте TerraX на бирже за земные кредиты.',
        'News & signals': 'Новости и сигналы',
        'Read the latest dispatches, leave comments, and watch the bell for notifications and security alerts.': 'Читайте свежие сводки, оставляйте комментарии и следите за колокольчиком — там уведомления и оповещения безопасности.',
        'Weather & alerts': 'Погода и оповещения',
        "Live weather for the settlement. Turn on browser push to get storm warnings even when you're away.": 'Погода в поселении в реальном времени. Включите push-уведомления браузера, чтобы получать штормовые предупреждения даже когда вас нет рядом.',
        'City services': 'Городские службы',
        'Transport timetables, health check-ups with Terra Watch, government tax and pension, and Terra Chat.': 'Расписание транспорта, медосмотры Terra Watch, налоги и пенсия, а также Terra Chat.',
        'Feedback & help': 'Отзывы и помощь',
        "Tell us what's broken or missing on the Feedback page. Adjust text size and contrast under accessibility.": 'Сообщите, что сломано или чего не хватает, на странице «Отзывы». Размер текста и контраст настраиваются в «Специальных возможностях».',
        'Back': 'Назад',
        'Next': 'Далее',
        'Got it': 'Понятно',
    },
}


def add(locale, data):
    path = PO_ROOT / locale / 'LC_MESSAGES' / 'django.po'
    text = path.read_text(encoding='utf-8')
    existing = set()
    for m in re.finditer(r'^msgid\s+("(?:[^"\\]|\\.)*")', text, re.M):
        existing.add(m.group(1))

    blocks = []
    for msgid, translation in data.items():
        if quote(msgid) in existing:
            print(f'{locale}: skip (exists) {msgid!r}')
            continue
        blocks.append(
            f'#: templates/base.html\n'
            f'msgid {quote(msgid)}\n'
            f'msgstr {quote(translation)}'
        )

    if blocks:
        out = text.rstrip('\n') + '\n' + '\n\n'.join(blocks) + '\n'
        path.write_text(out, encoding='utf-8')
        print(f'{locale}: appended {len(blocks)} entries')
    else:
        print(f'{locale}: nothing to append')


if __name__ == '__main__':
    for locale, data in TRANSLATIONS.items():
        add(locale, data)
