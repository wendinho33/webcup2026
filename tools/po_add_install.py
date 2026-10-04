"""Append PWA-install strings to each locale .po (no msgmerge bloat).

Run: python tools/po_add_install.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from po_add_tutorial import add  # noqa: E402

INSTALL = {
    'fr': {
        'Install app': "Installer l'application",
        'Terra Nova app installed.': 'Application Terra Nova installée.',
        'To install, tap Share and choose “Add to Home Screen”.': "Pour installer, touchez Partager puis choisissez « Ajouter à l'écran d'accueil ».",
    },
    'mg': {
        'Install app': 'Hampiditra ny fampiharana',
        'Terra Nova app installed.': 'Voaorina ny fampiharana Terra Nova.',
        'To install, tap Share and choose “Add to Home Screen”.': "Raha hampiditra, tsindrio ny Mizarà ary fidio ny « Ampiana amin'ny efijery fandraisana ».",
    },
    'mfe': {
        'Install app': 'Instal laplikasion',
        'Terra Nova app installed.': 'Laplikasion Terra Nova inn instale.',
        'To install, tap Share and choose “Add to Home Screen”.': 'Pou instale, tap Partaze ek swazir « Azout lor lekran lakaz ».',
    },
    'zh': {
        'Install app': '安装应用',
        'Terra Nova app installed.': 'Terra Nova 应用已安装。',
        'To install, tap Share and choose “Add to Home Screen”.': '要安装，请点击“分享”，然后选择“添加到主屏幕”。',
    },
    'ru': {
        'Install app': 'Установить приложение',
        'Terra Nova app installed.': 'Приложение Terra Nova установлено.',
        'To install, tap Share and choose “Add to Home Screen”.': 'Чтобы установить, нажмите «Поделиться» и выберите «На экран “Домой”».',
    },
}

if __name__ == '__main__':
    for locale, data in INSTALL.items():
        add(locale, data)
