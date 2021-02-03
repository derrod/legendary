#!/usr/bin/env python3

import gi
import webbrowser
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import legendary.core

def is_installed(app_name):
    if core.get_installed_game(app_name) == None:
        return "No"
    else:
        return "Yes"

def installed_size(app_name):
    g = core.get_installed_game(app_name)
    if g == None:
        return ""
    else:
        return f"{g.install_size / (1024*1024*1024):.02f} GiB"

def update_avail(app_name):
    print_version = False
    g = core.get_installed_game(app_name)
    if g != None:
        try:
            version = core.get_asset(app_name).build_version
        except ValueError:
            log_gtk(f'Metadata for "{game.app_name}" is missing, the game may have been removed from '
                           f'your account or not be in legendary\'s database yet, try rerunning the command '
                           f'with "--check-updates".')
        if version != g.version:
            if print_version: # for future config
                return f"Yes (Old: {g.version}; New: {version})"
            else:
                return f"Yes"
        else:
            return "No"
    else:
        return ""

def log_gtk(msg):
    dialog = Gtk.Dialog(title="Legendary Log")
    dialog.log = Gtk.Label(label=msg)
    dialog.log.set_selectable()
    box = dialog.get_content_area()
    box.add(dialog.log)
    dialog.show_all()

class main_window(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self,title="Legendary")
        #self.grid = Gtk.Grid(column_spacing=30, row_spacing=30)
        self.set_default_size(800, 600)
        self.box = Gtk.Box()
        self.add(self.box)

        # 'Legendary' label
        self.legendary_label = Gtk.Label(label="Legendary")
        self.login_vbox = Gtk.VBox()
        self.login_vbox.pack_start(self.legendary_label, False, False, 10)

        # Login button
        if not core.login():
            self.button_login = Gtk.Button(label="Login")
            self.button_login.connect("clicked", self.onclick)
            self.login_vbox.pack_start(self.button_login, False, False, 10)

        self.box.pack_start(self.login_vbox, False, False, 20)

        # Games
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_border_width(10)
        self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        self.box.pack_end(self.scroll, True, True, 0)
        self.scroll.games = Gtk.ListStore(str, str, str, str)
        gcols = ["Title","Installed","Size","Update Avaiable"]

        if not core.login():
            log_gtk('Login failed, cannot continue!')
        games, dlc_list = core.get_game_and_dlc_list()
        games = sorted(games, key=lambda x: x.app_title.lower())
        for citem_id in dlc_list.keys():
            dlc_list[citem_id] = sorted(dlc_list[citem_id], key=lambda d: d.app_title.lower())
        for game in games:
            ls = (  game.app_title,
                    is_installed(game.app_name),
                    installed_size(game.app_name),
                    update_avail(game.app_name)
                 )
            self.scroll.games.append(list(ls))
            #print(f' * {game.app_title} (App name: {game.app_name} | Version: {game.app_version})')
            for dlc in dlc_list[game.asset_info.catalog_item_id]:
                ls = (  dlc.app_title+f" (DLC of {game.app_title})",
                        is_installed(dlc.app_name),
                        installed_size(dlc.app_name),
                        update_avail(dlc.app_name)
                     )
                self.scroll.games.append(list(ls))
                #print(f'  + {dlc.app_title} (App name: {dlc.app_name} | Version: {dlc.app_version})')

        self.scroll.gview = Gtk.TreeView(Gtk.TreeModelSort(model=self.scroll.games))
        for i, c in enumerate(gcols):
            cell = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(c, cell, text=i)
            col.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            col.set_resizable(True)
            col.set_reorderable(True)
            col.set_sort_column_id(i)
            self.scroll.gview.append_column(col)

        l = Gtk.Label()
        l.set_text("")
        g = Gtk.Grid()
        g.attach(self.scroll.gview, 0, 0, 1, 1)
        g.attach(l, 0, 1, 1, 1)
        self.scroll.add(g)

        
    def onclick(self, widget):
        webbrowser.open('https://www.epicgames.com/id/login?redirectUrl=https%3A%2F%2Fwww.epicgames.com%2Fid%2Fapi%2Fredirect')
        exchange_token = ''
        sid = ask_sid(self)
        exchange_token = core.auth_sid(sid)
        if not exchange_token:
            log_gtk('No exchange token, cannot login.')
            return
        if core.auth_code(exchange_token):
            log_gtk(f'Successfully logged in as "{core.lgd.userdata["displayName"]}"')
        else:
            log_gtk('Login attempt failed, please see log for details.')

def ask_sid(parent):
    dialog = Gtk.MessageDialog(parent, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.QUESTION, Gtk.ButtonsType.OK_CANCEL)
    dialog.set_title("Enter Sid")
    #dialog.set_default_size(200, 200)

    label = Gtk.Label()
    label.set_markup("Please login via the epic web login, if web page did not open automatically, please manually open the following URL:\n<a href=\"https://www.epicgames.com/id/login?redirectUrl=https://www.epicgames.com/id/api/redirect\">https://www.epicgames.com/id/login?redirectUrl=https://www.epicgames.com/id/api/redirect</a>")
    entry = Gtk.Entry()
    box = dialog.get_content_area()
    box.pack_start(label, False, False, 0)
    box.add(entry)

    dialog.show_all()
    response = dialog.run()
    sid = entry.get_text()
    dialog.destroy()
    if response == Gtk.ResponseType.OK:
        return sid
    else:
        return 1

core = legendary.core.LegendaryCore()
win = main_window()

#log_gtk("This is another message wa wda dwah jkdwhajk dhwjkah djkahwjk hdjkwah jkawhjk dhawjkhd jkawh djkawhjk h")
#log_gtk("This is another message")

win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

#cli.logger.Handler = logw.log
#        for game in games:
#            print(f' * {game.app_title} (App name: {game.app_name} | Version: {game.app_version})')
#            for dlc in dlc_list[game.asset_info.catalog_item_id]:
#                print(f'  + {dlc.app_title} (App name: {dlc.app_name} | Version: {dlc.app_version})')
#
