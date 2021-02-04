import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

class log_dlm:
    def create(self, main_window):
        if main_window == "cli":
            print(main_window)
            return "cli"
        else:
            print(main_window)
            return main_window.progress_bar

    def update(self_log_dlm, self, perc, processed_chunks, num_chunk_tasks, rt_hours, rt_minutes, rt_seconds, hours, minutes, seconds, total_dl, total_write, total_used, dl_speed, dl_unc_speed, w_speed, r_speed, obj_out):
        print("update_choose")
        if obj_out == "cli":
            print("update_cli")
            self_log_dlm.update_cli(
                        self,
                        perc,
                        processed_chunks,
                        num_chunk_tasks,
                        rt_hours,
                        rt_minutes,
                        rt_seconds,
                        hours,
                        minutes,
                        seconds,
                        total_dl,
                        total_write,
                        total_used,
                        dl_speed,
                        dl_unc_speed,
                        w_speed,
                        r_speed)
        else:
            print("update_gui")
            self_log_dlm.update_gui(
                        self,
                        perc,
                        processed_chunks,
                        num_chunk_tasks,
                        rt_hours,
                        rt_minutes,
                        rt_seconds,
                        hours,
                        minutes,
                        seconds,
                        total_dl,
                        total_write,
                        total_used,
                        dl_speed,
                        dl_unc_speed,
                        w_speed,
                        r_speed,
                        obj_out)


    def update_gui(self_log_dlm, self, perc, processed_chunks, num_chunk_tasks, rt_hours, rt_minutes, rt_seconds, hours, minutes, seconds, total_dl, total_write, total_used, dl_speed, dl_unc_speed, w_speed, r_speed, bar):
        bar.set_fraction(perc)
        bar.set_text(f"{dl_speed / 1024 / 1024:.02f} MiB/s - {(perc*100):.02f}% - ETA: {hours:02d}:{minutes:02d}:{seconds:02d}")
        print(bar.get_text())

    def update_cli(self_log_dlm, self, perc, processed_chunks, num_chunk_tasks, rt_hours, rt_minutes, rt_seconds, hours, minutes, seconds, total_dl, total_write, total_used, dl_speed, dl_unc_speed, w_speed, r_speed):
        perc *= 100
        print(f"perc: {perc}")
        self.log.info(f'= Progress: {perc:.02f}% ({processed_chunks}/{num_chunk_tasks}), '
                      f'Running for {rt_hours:02d}:{rt_minutes:02d}:{rt_seconds:02d}, '
                      f'ETA: {hours:02d}:{minutes:02d}:{seconds:02d}')
        self.log.info(f' - Downloaded: {total_dl / 1024 / 1024:.02f} MiB, '
                      f'Written: {total_write / 1024 / 1024:.02f} MiB')
        self.log.info(f' - Cache usage: {total_used} MiB, active tasks: {self.active_tasks}')
        self.log.info(f' + Download\t- {dl_speed / 1024 / 1024:.02f} MiB/s (raw) '
                      f'/ {dl_unc_speed / 1024 / 1024:.02f} MiB/s (decompressed)')
        self.log.info(f' + Disk\t- {w_speed / 1024 / 1024:.02f} MiB/s (write) / '
                      f'{r_speed / 1024 / 1024:.02f} MiB/s (read)')












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
