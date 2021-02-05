import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

class log_dlm:
    def create(self_log_dlm, self, main_window):
        if main_window == "cli":
            print(main_window)
            return "cli"
        else:
            print(main_window)
            self_log_dlm.update_gui_setup(self_log_dlm=self_log_dlm, self=self, bar=main_window.progress_bar)
            #return main_window.progress_bar

    def update(self_log_dlm, self):
            #perc, processed_chunks, num_chunk_tasks, rt_hours, rt_minutes, rt_seconds, hours, minutes, seconds, total_dl, total_write, total_used, dl_speed, dl_unc_speed, w_speed, r_speed, obj_out):
        print("update_choose")
        if self.obj_out == "cli":
            print("update_cli")
            self_log_dlm.update_cli(self)
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
            #self_log_dlm.update_gui(
            #           self,
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

    def update_gui_setup(self_log_dlm = None, self = None, bar = None):
        GLib.timeout_add(1000, self_log_dlm.update_gui,
                        self.self, self.perc,
                        self.processed_chunks, self.num_chunk_tasks,
                        self.rt_hours, self.rt_minutes, self.rt_seconds,
                        self.hours, self.minutes, self.seconds,
                        self.total_dl, self.total_write, self.total_used,
                        self.dl_speed, self.dl_unc_speed, self.w_speed, self.r_speed,
                        bar)

    def update_gui(self_log_dlm, self,
                   # perc,
                   # processed_chunks, num_chunk_tasks,
                   # rt_hours, rt_minutes, rt_seconds,
                   # hours, minutes, seconds,
                   # total_dl, total_write, total_used,
                   # dl_speed, dl_unc_speed, w_speed, r_speed,
                   bar):
        bar.set_fraction(perc)
        bar.set_text(f"{self.dl_speed / 1024 / 1024:.02f} MiB/s - {(self.perc*100):.02f}% - ETA: {self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}")
        bar.set_tooltip_text("tooltip") # show all infos that are also in update_cli()
        print(bar.get_text())
        return True # since this is a timeout function

    def update_cli(self_log_dlm, self)
            #perc,
            #processed_chunks, num_chunk_tasks,
            #rt_hours, rt_minutes, rt_seconds,
            #hours, minutes, seconds,
            #total_dl, total_write, total_used,
            #dl_speed, dl_unc_speed, w_speed, r_speed):
        perc = self.perc * 100
        print(f"perc: {perc}%")
        self.log.info(f'= Progress: {perc:.02f}% ({self.processed_chunks}/{self.num_chunk_tasks}), '
                      f'Running for {self.rt_hours:02d}:{self.rt_minutes:02d}:{self.rt_seconds:02d}, '
                      f'ETA: {self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}')
        self.log.info(f' - Downloaded: {self.total_dl / 1024 / 1024:.02f} MiB, '
                      f'Written: {self.total_write / 1024 / 1024:.02f} MiB')
        self.log.info(f' - Cache usage: {self.total_used} MiB, active tasks: {self.active_tasks}')
        self.log.info(f' + Download\t- {self.dl_speed / 1024 / 1024:.02f} MiB/s (raw) '
                      f'/ {self.dl_unc_speed / 1024 / 1024:.02f} MiB/s (decompressed)')
        self.log.info(f' + Disk\t- {self.w_speed / 1024 / 1024:.02f} MiB/s (write) / '
                      f'{self.r_speed / 1024 / 1024:.02f} MiB/s (read)')












#
#        self.log.info(f'= Progress: {perc:.02f}% ({processed_chunks}/{num_chunk_tasks}), '
#                      f'Running for {rt_hours:02d}:{rt_minutes:02d}:{rt_seconds:02d}, '
#                      f'ETA: {hours:02d}:{minutes:02d}:{seconds:02d}')
#        self.log.info(f' - Downloaded: {total_dl / 1024 / 1024:.02f} MiB, '
#                      f'Written: {total_write / 1024 / 1024:.02f} MiB')
#        self.log.info(f' - Cache usage: {total_used} MiB, active tasks: {self.active_tasks}')
#        self.log.info(f' + Download\t- {dl_speed / 1024 / 1024:.02f} MiB/s (raw) '
#                      f'/ {dl_unc_speed / 1024 / 1024:.02f} MiB/s (decompressed)')
#        self.log.info(f' + Disk\t- {w_speed / 1024 / 1024:.02f} MiB/s (write) / '
#                      f'{r_speed / 1024 / 1024:.02f} MiB/s (read)')

        #task = update_gui_task(self_log_dlm, self, perc, processed_chunks, num_chunk_tasks, rt_hours, rt_minutes, rt_seconds, hours, minutes, seconds, total_dl, total_write, total_used, dl_speed, dl_unc_speed, w_speed, r_speed, bar)
