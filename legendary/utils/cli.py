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
