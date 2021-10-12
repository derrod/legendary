from string import ascii_lowercase, digits

# Aliases generated:
# - name lowercase (without TM etc.)
# - same, but without spaces
# - same, but roman numerals are replaced
# if name has >= 2 parts:
# - initials
# - initials, but roman numerals are intact
# - initials, but roman numerals are replaced with number
# if ':' in name:
# - run previous recursively with everything before ":"
# if single 'f' in long word:
# - split word (this is mainly for cases like Battlfront -> BF)
# the first word longer than 1 character that isn't "the", "for", or "of" will also be added

allowed_characters = ascii_lowercase+digits
roman = {
    'i': '1',
    'ii': '2',
    'iii': '3',
    'iv': '4',
    'v': '5',
    'vi': '6',
    'vii': '7',
    'viii': '8',
    'ix': '9',
    'x': '10',
    'xi': '11',
    'xii': '12',
    'xiii': '13',
    'xiv': '14',
    'xv': '15',
    'xvi': '16',
    'xvii': '17',
    'xviii': '18',
    'xix': '19',
    'xx': '20'
}


def _filter(input):
    return ''.join(l for l in input if l in allowed_characters)


def generate_aliases(game_name, game_folder=None, split_words=True, app_name=None):
    # normalise and split name, then filter for legal characters
    game_parts = [_filter(p) for p in game_name.lower().split()]
    # filter out empty parts
    game_parts = [p for p in game_parts if p]

    _aliases = [
        game_name.lower().strip(),
        ' '.join(game_parts),
        ''.join(game_parts),
        ''.join(roman.get(p, p) for p in game_parts),
    ]

    # single word abbreviation
    try:
        first_word = next(i for i in game_parts if i not in ('for', 'the', 'of'))
        if len(first_word) > 1:
            _aliases.append(first_word)
    except StopIteration:
        pass

    # remove subtitle from game
    if ':' in game_name:
        _aliases.extend(generate_aliases(game_name.partition(':')[0]))
    if '-' in game_name:
        _aliases.extend(generate_aliases(game_name.replace('-', ' ')))
    # include folder name for alternative short forms
    if game_folder:
        _aliases.extend(generate_aliases(game_folder, split_words=False))
    # include lowercase version of app name in aliases
    if app_name:
        _aliases.append(app_name.lower())
    # include initialisms
    if len(game_parts) > 1:
        _aliases.append(''.join(p[0] for p in game_parts))
        _aliases.append(''.join(p[0] if p not in roman else p for p in game_parts))
        _aliases.append(''.join(roman.get(p, p[0]) for p in game_parts))
    # Attempt to address cases like "Battlefront" being shortened to "BF"
    if split_words:
        new_game_parts = []
        for word in game_parts:
            if len(word) >= 8 and word[3:-3].count('f') == 1:
                word_middle = word[3:-3]
                word_split = ' f'.join(word_middle.split('f'))
                word = word[0:3] + word_split + word[-3:]
                new_game_parts.extend(word.split())
            else:
                new_game_parts.append(word)

        if len(new_game_parts) > 1:
            _aliases.append(''.join(p[0] for p in new_game_parts))
            _aliases.append(''.join(p[0] if p not in roman else p for p in new_game_parts))
            _aliases.append(''.join(roman.get(p, p[0]) for p in new_game_parts))

    # return sorted uniques
    return sorted(set(_aliases))
