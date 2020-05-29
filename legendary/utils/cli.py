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
