def get_boolean_choice(prompt, default=True):
    if default:
        yn = 'Y/n'
    else:
        yn = 'y/N'

    choice = input(f'{prompt} [{yn}]: ')
    if not choice:
        return default
    elif choice[0].lower() == 'y':
        return True
    else:
        return False


def sdl_prompt(sdl_data, title):
    tags = ['']
    if '__required' in sdl_data:
        tags.extend(sdl_data['__required']['tags'])

    print(f'You are about to install {title}, this application supports selective downloads.')
    print('The following optional packs are available (tag - name):')
    for tag, info in sdl_data.items():
        if tag == '__required':
            continue
        print(' *', tag, '-', info['name'])

    examples = ', '.join([g for g in sdl_data.keys() if g != '__required'][:2])
    print(f'Please enter tags of pack(s) to install (space/comma-separated, e.g. "{examples}")')
    print('Leave blank to use defaults (only required data will be downloaded).')
    choices = input(f'Additional packs [Enter to confirm]: ')
    if not choices:
        return tags

    for c in choices.strip('"').replace(',', ' ').split():
        c = c.strip()
        if c in sdl_data:
            tags.extend(sdl_data[c]['tags'])
        else:
            print('Invalid tag:', c)

    return tags


def strtobool(val):
    """Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.

    Copied from python standard library as distutils.util.strtobool is deprecated.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return 1
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))

