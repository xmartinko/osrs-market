"""Small recorded response excerpts, fetched 2026-10-30 using the research User-Agent.

Full payloads/evidence stay outside git. These excerpts are parser test code.
"""
WG = {'4151': [{'id': '4151', 'price': 2057864, 'volume': None,
                'timestamp': 1427500800000},
               {'id': '4151', 'price': 2072694, 'volume': None,
                'timestamp': 1427587200000}]}
WIKI = {'timestamp': 1793379900, 'data': {'2': {
    'avgHighPrice': 205.61, 'highPriceVolume': 58893,
    'avgLowPrice': 198.13, 'lowPriceVolume': 57248}}}
KAGGLE = {'itemId': 2, 'timestamp': 5383963, 'avgLowPrice': 159,
          'avgHighPrice': 161, 'lowPriceVolume': 394, 'highPriceVolume': 50300}
LUA = """return {
    itemId     = 4151,
    price      = 2790107,
    volume     = 6510,
    date       = '23 March 2019 00:00:00 (UTC)',
    volumeDate = '23 March 2019 00:00:00 (UTC)',
    item       = 'Abyssal whip',
}"""
MONSTER = {'1': {'id': 1, 'name': 'Molanisk', 'last_updated': '2021-09-02',
                  'incomplete': True, 'drops': [
                      {'id': 1623, 'name': 'Uncut sapphire', 'members': True,
                       'quantity': '1', 'noted': False, 'rarity': 0.013671875, 'rolls': 1}]}}
