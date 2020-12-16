# This file contains definitions for selective downloading for supported games
# coding: utf-8

_cyberpunk_sdl = {
    'de': {'tags': ['voice_de_de'], 'name': 'Deutsch'},
    'es': {'tags': ['voice_es_es'], 'name': 'español (España)'},
    'fr': {'tags': ['voice_fr_fr'], 'name': 'français'},
    'it': {'tags': ['voice_it_it'], 'name': 'italiano'},
    'ja': {'tags': ['voice_ja_jp'], 'name': '日本語'},
    'ko': {'tags': ['voice_ko_kr'], 'name': '한국어'},
    'pl': {'tags': ['voice_pl_pl'], 'name': 'polski'},
    'pt': {'tags': ['voice_pt_br'], 'name': 'português brasileiro'},
    'ru': {'tags': ['voice_ru_ru'], 'name': 'русский'},
    'cn': {'tags': ['voice_zh_cn'], 'name': '中文（中国）'}
}

_fortnite_sdl = {
    '__required': {'tags': ['chunk0', 'chunk10'], 'name': 'Fortnite Core'},
    'stw': {'tags': ['chunk11', 'chunk11optional'], 'name': 'Fortnite Save the World'},
    'hd_textures': {'tags': ['chunk10optional'], 'name': 'High Resolution Textures'},
    'lang_de': {'tags': ['chunk2'], 'name': '(Language Pack) Deutsch'},
    'lang_fr': {'tags': ['chunk5'], 'name': '(Language Pack) français'},
    'lang_pl': {'tags': ['chunk7'], 'name': '(Language Pack) polski'},
    'lang_ru': {'tags': ['chunk8'], 'name': '(Language Pack) русский'},
    'lang_cn': {'tags': ['chunk9'], 'name': '(Language Pack) 中文（中国）'}
}

games = {
    'Fortnite': _fortnite_sdl,
    'Ginger': _cyberpunk_sdl
}


def get_sdl_appname(app_name):
    for k in games.keys():
        if app_name.startswith(k):
            return k
    return None
