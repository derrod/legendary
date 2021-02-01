from legendary.utils.selective_dl import games


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


def sdl_prompt(app_name, title):
    tags = ['']
    if '__required' in games[app_name]:
        tags.extend(games[app_name]['__required']['tags'])

    print(f'You are about to install {title}, this game supports selective downloads.')
    print('The following optional packs are available:')
    for tag, info in games[app_name].items():
        if tag == '__required':
            continue
        print(' *', tag, '-', info['name'])

    print('Please enter a comma-separated list of optional packs to install (leave blank for defaults)')
    examples = ','.join([g for g in games[app_name].keys() if g != '__required'][:2])
    choices = input(f'Additional packs [e.g. {examples}]: ')
    if not choices:
        return tags

    for c in choices.split(','):
        c = c.strip()
        if c in games[app_name]:
            tags.extend(games[app_name][c]['tags'])
        else:
            print('Invalid tag:', c)

    return tags
