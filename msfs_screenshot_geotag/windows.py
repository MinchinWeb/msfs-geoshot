from typing import List, NamedTuple, Optional

import psutil
import win32gui
import win32process


class WindowRectangle(NamedTuple):
    left: int
    top: int
    right: int
    bottom: int


def get_window_ids_by_process_name(process_name: str) -> List[int]:

    target_pid: Optional[int] = None

    for process in psutil.process_iter():
        if process.name() == process_name:
            target_pid = process.pid
            # assumes there is only one process to look at
            break
    else:
        raise OSError(f"Could not find process ID for '{process_name}'")

    matching_window_ids: List[int] = []

    def enum_cb(window_id: int, window_list: List[int]):
        if not win32gui.IsWindowVisible(window_id):  # type: ignore[arg]
            return
        _, process_id = win32process.GetWindowThreadProcessId(window_id)  # type: ignore[arg]
        process = psutil.Process(process_id)
        if process_id == target_pid:
            window_list.append(window_id)

    win32gui.EnumWindows(enum_cb, matching_window_ids)  # type: ignore[arg]

    return matching_window_ids


def get_window_title_by_window_id(window_id: int) -> str:
    return win32gui.GetWindowText(window_id)  # type: ignore


def raise_window_to_foreground(window_id: int):
    win32gui.SetForegroundWindow(window_id)  # type: ignore


def get_window_rectangle(window_id: int) -> WindowRectangle:
    return WindowRectangle(*win32gui.GetWindowRect(window_id))  # type: ignore
