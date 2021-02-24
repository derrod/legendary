import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

class log_dlm:
    def create(self, dlm, main_window):
        if main_window == "cli":
            print("cli",main_window.get_title(),main_window)
            return "cli"
        else:
            print("bar",main_window.get_title(),main_window)
            #self.update_gui_setup(dlm=dlm, bar=main_window.progress_bar)
            #self.update_gui_setup(dlm, main_window.progress_bar)
            print(main_window.progress_bar)
            return main_window.progress_bar

    def update(self, dlm):
            #perc, processed_chunks, num_chunk_tasks, rt_hours, rt_minutes, rt_seconds, hours, minutes, seconds, total_dl, total_write, total_used, dl_speed, dl_unc_speed, w_speed, r_speed, obj_out):
        print("update_choose")
        if dlm.obj_out == "cli":
            print("update_cli")
            self.update_cli(dlm)
                        #perc,
                        #processed_chunks,
                        #num_chunk_tasks,
                        #rt_hours,
                        #rt_minutes,
                        #rt_seconds,
                        #hours,
                        #minutes,
                        #seconds,
                        #total_dl,
                        #total_write,
                        #total_used,
                        #dl_speed,
                        #dl_unc_speed,
                        #w_speed,
                        #r_speed)
        else:
            print("update_gui")
            print(f"{dlm.dl_speed / 1024 / 1024:.02f} MiB/s - {(dlm.perc*100):.02f}% - ETA: {dlm.hours:02d}:{dlm.minutes:02d}:{dlm.seconds:02d} - log_dlm")
            #self.update_gui(dlm, dlm.obj_out)
            #self.update_gui(
            #           dlm,
            #           perc,
            #           processed_chunks,
            #           num_chunk_tasks,
            #           rt_hours,
            #           rt_minutes,
            #           rt_seconds,
            #           hours,
            #           minutes,
            #           seconds,
            #           total_dl,
            #           total_write,
            #           total_used,
            #           dl_speed,
            #           dl_unc_speed,
            #           w_speed,
            #           r_speed,
            #           obj_out)

    #def update_gui_setup(self, dlm = None, bar = None):
    def update_gui_setup(self, dlm, bar):
        self.timeout_id = GLib.timeout_add(50, self.update_gui, dlm, bar)
        print("timeout_add -",self.timeout_id)
        #Glib.threads_init()
        #print("threads_init")

    def update_gui(self, dlm, bar):
                   # perc,
                   # processed_chunks, num_chunk_tasks,
                   # rt_hours, rt_minutes, rt_seconds,
                   # hours, minutes, seconds,
                   # total_dl, total_write, total_used,
                   # dl_speed, dl_unc_speed, w_speed, r_speed,
        print(f"update_gui_{bar}")
        bar.set_fraction(dlm.perc)
        bar.set_text(f"{dlm.dl_speed / 1024 / 1024:.02f} MiB/s - {(dlm.perc*100):.02f}% - ETA: {dlm.hours:02d}:{dlm.minutes:02d}:{dlm.seconds:02d}")
        bar.set_tooltip_text("tooltip") # show all infos that are also in update_cli()
        print(bar.get_text())
        return True # since this is a timeout function

    def update_cli(self, dlm):
            #perc,
            #processed_chunks, num_chunk_tasks,
            #rt_hours, rt_minutes, rt_seconds,
            #hours, minutes, seconds,
            #total_dl, total_write, total_used,
            #dl_speed, dl_unc_speed, w_speed, r_speed
            #):
        perc = dlm.perc * 100
        print(f"perc: {perc}%")
        print(f"{dlm}")
        print(f"hexid:{hex(id(dlm.perc))}")
        #dlm.log.info(f'= Progress: {perc:.02f}% ({dlm.processed_chunks}/{dlm.num_chunk_tasks}), '
        #              f'Running for {dlm.rt_hours:02d}:{dlm.rt_minutes:02d}:{dlm.rt_seconds:02d}, '
        #              f'ETA: {dlm.hours:02d}:{dlm.minutes:02d}:{dlm.seconds:02d}')
        #dlm.log.info(f' - Downloaded: {dlm.total_dl / 1024 / 1024:.02f} MiB, '
        #              f'Written: {dlm.total_write / 1024 / 1024:.02f} MiB')
        #dlm.log.info(f' - Cache usage: {dlm.total_used} MiB, active tasks: {dlm.active_tasks}')
        #dlm.log.info(f' + Download\t- {dlm.dl_speed / 1024 / 1024:.02f} MiB/s (raw) '
        #              f'/ {dlm.dl_unc_speed / 1024 / 1024:.02f} MiB/s (decompressed)')
        #dlm.log.info(f' + Disk\t- {dlm.w_speed / 1024 / 1024:.02f} MiB/s (write) / '
        #              f'{dlm.r_speed / 1024 / 1024:.02f} MiB/s (read)')












#
#        dlm.log.info(f'= Progress: {perc:.02f}% ({processed_chunks}/{num_chunk_tasks}), '
#                      f'Running for {rt_hours:02d}:{rt_minutes:02d}:{rt_seconds:02d}, '
#                      f'ETA: {hours:02d}:{minutes:02d}:{seconds:02d}')
#        dlm.log.info(f' - Downloaded: {total_dl / 1024 / 1024:.02f} MiB, '
#                      f'Written: {total_write / 1024 / 1024:.02f} MiB')
#        dlm.log.info(f' - Cache usage: {total_used} MiB, active tasks: {dlm.active_tasks}')
#        dlm.log.info(f' + Download\t- {dl_speed / 1024 / 1024:.02f} MiB/s (raw) '
#                      f'/ {dl_unc_speed / 1024 / 1024:.02f} MiB/s (decompressed)')
#        dlm.log.info(f' + Disk\t- {w_speed / 1024 / 1024:.02f} MiB/s (write) / '
#                      f'{r_speed / 1024 / 1024:.02f} MiB/s (read)')

        #task = update_gui_task(self, dlm, perc, processed_chunks, num_chunk_tasks, rt_hours, rt_minutes, rt_seconds, hours, minutes, seconds, total_dl, total_write, total_used, dl_speed, dl_unc_speed, w_speed, r_speed, bar)
