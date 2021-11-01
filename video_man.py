import os
import time
import traceback
from pyside import QtCore, QtWidgets

import image_stub
import widgets

IMG = image_stub.IMG
ARGS = '-f gdigrab -draw_mouse {pointer} -framerate {fps} -offset_x {x} -offset_y {y} -video_size {w}x{h} -show_region 0 -i desktop -b:v {quality}k'
TMP_NAME = '_kiekste_tmp'
TMP_PATH = os.path.join(os.getenv('TEMP', ''), TMP_NAME)
WMIC_TMP = 'wmic.exe process where {} get Name,ProcessID'
WMIC_PID = 'ProcessID={}'
WMIC_NAME = 'Name="{}"'
TOOL_NAME = 'ffmpeg.exe'


class VideoMan(QtCore.QObject):
    video_found = QtCore.Signal()
    capture_stopped = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.path = ''
        self.capturing = False
        self.thread = None  # type: _CaptureThread | None
        QtCore.QTimer(self).singleShot(500, self._find_ffmpeg)

    def _find_ffmpeg(self):
        thread = _FFMPegFinder(self)
        thread.found.connect(self._ffmpeg_found)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _ffmpeg_found(self, path: str):
        if not os.path.isfile(path):
            return
        self.path = path
        self.video_found.emit()

    def capture(self, rect):
        # type: (QtCore.QRectF | QtCore.QRect) -> None
        import uuid

        os.makedirs(TMP_PATH, exist_ok=True)
        out_file = os.path.join(TMP_PATH, f'_tmp_video{uuid.uuid4()}.mp4')
        if os.path.isfile(out_file):
            os.unlink(out_file)

        settings = self.parent().settings
        capture_settings = {
            'x': rect.x(),
            'y': rect.y(),
            'w': rect.width(),
            'h': rect.height(),
            'fps': settings.video_fps,
            'quality': settings.video_quality,
            'pointer': int(settings.draw_pointer),
            'out_path': out_file,
        }

        self.capturing = True
        self.thread = _CaptureThread(self, self.path, capture_settings)
        self.thread.stopped.connect(self.on_stopped)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def stop(self):
        if self.thread is None:
            return
        self.thread.requestInterruption()

    def on_stopped(self):
        try:
            print('self.thread stopped: %s\n' % self.thread)
            self.capturing = False
        except KeyboardInterrupt:
            print('KeyboardInterrupt catched!')
            pass
        QtCore.QTimer(self).singleShot(250, self.capture_stopped.emit)


class _CaptureThread(QtCore.QThread):
    progress = QtCore.Signal(dict)
    stopped = QtCore.Signal()

    def __init__(self, parent, path, settings):
        super().__init__(parent)

        self.path = path
        self.settings = settings

        # how to deal with output? Do we need it?
        # subprocess needs file like objs to pipe to. These also need `.fileno`
        # so StringIO doesn't do! :/ We could open real files to pipe to:
        self._strout_file = os.path.join(TMP_PATH, '_tmpout.log')
        self._strerr_file = os.path.join(TMP_PATH, '_tmperr.log')

    def run(self):
        # I'd love to use `QProcess` right away but had massive problems so far.
        # process = QtCore.QProcess()
        # process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        import subprocess, signal

        arglist = [self.path]
        arglist.extend(ARGS.format_map(self.settings).split())
        arglist.append(self.settings['out_path'])

        tmp_stdout_fob = open(self._strout_file, 'w')
        tmp_stderr_fob = open(self._strerr_file, 'w')

        nfo = _hidden_proc_nfo()

        pids_b4 = get_pids(TOOL_NAME)
        print('pids_b4: %s' % pids_b4)
        process = subprocess.Popen(
            arglist, shell=True, stdout=tmp_stdout_fob, stderr=tmp_stderr_fob, startupinfo=nfo
        )
        print(f'running process {process.pid}:{process} ...')
        new_pids = pids_b4 - get_pids(TOOL_NAME)
        slept = 0
        while not new_pids:
            self.msleep(10)
            new_pids = pids_b4 - get_pids(TOOL_NAME)
            slept += 10
            if slept > 1000:
                raise RuntimeError(f'No new {TOOL_NAME} spawned!')

        print('new_pids: %s' % new_pids)
        if new_pids:
            ffmpid = new_pids.pop()
            print('ffmpid: %s' % ffmpid)
        else:
            raise RuntimeError(f'No new {TOOL_NAME} spawned!')

        while True:
            if self.isInterruptionRequested():
                try:
                    os.kill(ffmpid, signal.CTRL_C_EVENT)
                    # process.send_signal(signal.CTRL_C_EVENT)
                except (OSError, SystemError) as error:
                    print('error: %s' % error)
                    print(traceback.format_exc().strip())

                    cmd = WMIC_TMP.format(WMIC_NAME.format(TOOL_NAME))
                    output = subprocess.check_output(cmd, startupinfo=nfo).strip()
                    print('output after error: %s' % output)

                self.msleep(100)
                self.stopped.emit()
                break

            self.msleep(100)

        # sticking around as long as process would be running ...
        cmd = WMIC_TMP.format(WMIC_PID.format(process.pid))
        while True:
            output = subprocess.check_output(cmd, startupinfo=nfo).strip()
            if not output:
                print('process is gone!')
                break
            print('output: %s' % output)
            self.msleep(200)

        tmp_stdout_fob.close()
        tmp_stderr_fob.close()




def run_shell_process(name, arglist, stdout, tmp_stderr_fob):
    import subprocess



    parent_process = subprocess.Popen(
            arglist, shell=True, stdout=tmp_stdout_fob, stderr=tmp_stderr_fob, startupinfo=_hidden_proc_nfo()
    )


class _FFMPegFinder(QtCore.QThread):
    found = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

    def run(self):
        found = _find_ffmpeg()
        if found:
            self.found.emit(found)


class VideoWidget(QtWidgets.QWidget):
    def __init__(self, parent, videoman):
        super().__init__(parent)
        self.videoman = videoman
        self.hlayout = QtWidgets.QHBoxLayout(self)
        self.hlayout.setContentsMargins(5, 5, 5, 5)

        # QtWidgets.QLCDNumber
        self._t0 = time.time()
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._set_label)
        self._timer.setInterval(100)
        self.label = QtWidgets.QLabel()
        self.hlayout.addWidget(self.label)
        widgets._TbBtn(self, IMG.x, self.stop)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self._timer.start()

    def stop(self):
        self.videoman.stop()
        self._timer.stop()
        self.deleteLater()

    def _set_label(self):
        self.label.setText(str(time.time() - self._t0))


def _find_ffmpeg():
    import subprocess

    nfo = subprocess.STARTUPINFO()
    nfo.wShowWindow = subprocess.SW_HIDE
    nfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        found = subprocess.check_output(['where', TOOL_NAME], startupinfo=nfo)
        return found.decode().strip()
    except subprocess.CalledProcessError:
        return ''


def _hidden_proc_nfo():
    import subprocess

    nfo = subprocess.STARTUPINFO()
    nfo.wShowWindow = subprocess.SW_HIDE
    nfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return nfo


def get_pids(name):
    import subprocess

    nfo = _hidden_proc_nfo()
    cmd = WMIC_TMP.format(WMIC_NAME.format(name))
    pids = set()
    for line in subprocess.check_output(cmd, startupinfo=nfo).strip().decode().split('\n')[1:]:
        this_name, pid = line.rstrip().rsplit(' ', 1)
        if this_name.rstrip() == name and pid.isdigit():
            pids.add(int(pid))
    return pids


if __name__ == '__main__':
    import subprocess

    t0 = time.time()
    name = 'explorer.exe'
    pids = get_pids('explorer.exe')
    print('pids: %s' % pids)

    proc = subprocess.call([name], shell=False)

    print('proc: %s' % proc)
    new_pids = get_pids('cmd.exe')
    print('new_pids: %s' % new_pids)
    n = new_pids - pids
    print('n: %s' % n)
