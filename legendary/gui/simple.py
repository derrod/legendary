#!/usr/bin/env python3

import gi
import webbrowser
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from legendary.cli import LegendaryCLI

class MyWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self,title="Legendary")
        self.button = Gtk.Button(label="Login")
        self.button.connect("clicked", self.onclick)
        self.add(self.button)
    def onclick(self, widget):
        webbrowser.open('https://www.epicgames.com/id/login?redirectUrl=https%3A%2F%2Fwww.epicgames.com%2Fid%2Fapi%2Fredirect')
        sid = AskSid(self)
        print(f'LegendaryCLI.auth(f"--sid {sid}")')
        cli = LegendaryCLI()
        cli.main()
        a = {"session_id":sid}
        cli.auth(a)

def AskSid(parent):
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

win = MyWindow()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
