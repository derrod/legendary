#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

win = Gtk.Window()
grid = Gtk.Grid()
win.add(grid)
quit = Gtk.Button(label="Quit")
quit.set_size_request(80,30)
quit.connect("clicked", Gtk.main_quit)

grid.attach(quit,0,0,1,1)
win.set_border_width(10)
win.set_title("qq")
win.connect("destroy", Gtk.main_quit)
win.show()
Gtk.main()
