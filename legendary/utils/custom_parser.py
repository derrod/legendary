import argparse


class HiddenAliasSubparsersAction(argparse._SubParsersAction):
    def add_parser(self, name, **kwargs):
        # set prog from the existing prefix
        if kwargs.get('prog') is None:
            kwargs['prog'] = f'{self._prog_prefix} {name}'

        aliases = kwargs.pop('aliases', ())
        hide_aliases = kwargs.pop('hide_aliases', False)

        # create a pseudo-action to hold the choice help
        if 'help' in kwargs:
            help = kwargs.pop('help')
            _aliases = None if hide_aliases else aliases
            choice_action = self._ChoicesPseudoAction(name, _aliases, help)
            self._choices_actions.append(choice_action)

        # create the parser and add it to the map
        parser = self._parser_class(**kwargs)
        self._name_parser_map[name] = parser

        # make parser available under aliases also
        for alias in aliases:
            self._name_parser_map[alias] = parser

        return parser
