from pathlib import Path
from typing import Optional

from msfs_screenshot_geotag.exif import ExifData, ExifService
from msfs_screenshot_geotag.names import FileNameComposer
from msfs_screenshot_geotag.sim import SimService, SimServiceError
from PyQt5.QtCore import QEvent, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QCloseEvent, QDesktopServices, QKeySequence
from PyQt5.QtWidgets import QApplication, QFileDialog, QLineEdit, QMainWindow

from .. import __app_name__
from .forms.main_window import Ui_MainWindow
from .keyedit import CustomKeySequenceEdit
from .notification import NotificationColor, NotificationHandler
from .screenshots import ImageFormat, ScreenshotService
from .settings import AppSettings
from .validators import DateFormatValidator, FileNameFormatValidator

mock_exif_data = ExifData(
    GPSLatitude=30,
    GPSLongitude=30,
    GPSAltitude=100,
    GPSSpeed=200,  # m/s to km/h
)


class MainWindow(QMainWindow):

    closed = pyqtSignal()

    _maps_url = "https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"

    def __init__(
        self,
        sim_service: SimService,
        exif_service: ExifService,
        screenshot_service: ScreenshotService,
        settings: AppSettings,
        file_name_composer: FileNameComposer,
    ):
        super().__init__()

        self._sim_service = sim_service
        self._exif_service = exif_service
        self._screenshot_service = screenshot_service
        self._file_name_composer = file_name_composer
        self._settings = settings

        self._last_screenshot: Optional[Path] = None
        self._last_exif_data: Optional[ExifData] = None

        self._notification_handler = NotificationHandler(parent=self)

        self._form = Ui_MainWindow()
        self._form.setupUi(self)

        self._select_hotkey = CustomKeySequenceEdit(parent=self)
        self._form.layout_select_hotkey.addWidget(self._select_hotkey)
        self._form.open_screenshots.setFocus()  # prevent focus steal by hotkey

        self._load_ui_state_from_settings()
        self._setup_input_validators()
        self._setup_format_field_description()
        self._setup_button_labels()

        self._setup_input_widget_connections()
        self._setup_button_connections()

        self.setWindowTitle(__app_name__)

    @pyqtSlot()
    def take_screenshot(self) -> bool:
        try:
            exif_data = self._sim_service.get_flight_data()
        except SimServiceError as e:
            # print(e)
            # self._notification_handler.notify(
            #     message="<b>Error</b>: Could not connect to Simulator<br>or received invalid data",
            #     color=NotificationColor.error,
            # )
            exif_data = mock_exif_data  # DEBUG
            # return False

        screenshot = self._screenshot_service.take_screenshot(
            target_folder=self._settings.screenshot_folder,
            file_name_format=self._settings.file_name_format,
            date_format=self._settings.date_format,
            exif_data=exif_data,
            image_format=self._settings.image_format,
        )

        if exif_data:
            if not self._exif_service.write_data(
                image_path=screenshot, exif_data=exif_data
            ):
                self._notification_handler.notify(
                    message="<b>Error</b>: Could not write metadata to screenshot",
                    color=NotificationColor.error,
                )
                return False

        self._notification_handler.notify(
            message=f"<b>Screenshot saved</b>: {screenshot.name}",
            color=NotificationColor.success,
        )

        self._set_last_opened_screenshot(path=screenshot, exif_data=exif_data)

        return True

    def _setup_format_field_description(self):
        supported_fields = self._file_name_composer.get_supported_fields()

        lines = []

        for field in supported_fields:
            text = f"<b>{{{field.name}}}</b>: {field.description}"
            if field.required:
                text += " Required."
            lines.append(text)

        text = "<br>".join(lines)

        self._form.available_fields.setText(text)

    def _setup_input_validators(self):
        self._file_name_format_validator = FileNameFormatValidator(
            line_edit=self._form.file_name_format,
            warning_label=self._form.file_name_format_warning,
            save_button=self._form.file_name_format_save,
            file_name_composer=self._file_name_composer,
            parent=self,
        )
        self._date_format_validator = DateFormatValidator(
            line_edit=self._form.date_format,
            warning_label=self._form.date_format_warning,
            save_button=self._form.date_format_save,
            file_name_composer=self._file_name_composer,
            parent=self,
        )
        self._form.file_name_format.setValidator(self._file_name_format_validator)
        self._form.date_format.setValidator(self._date_format_validator)

    def _setup_button_connections(self):
        self._form.take_screenshot.clicked.connect(self.take_screenshot)
        self._form.quit_button.clicked.connect(
            self._on_quit_button, Qt.ConnectionType.QueuedConnection
        )  # queued connection recommended on slots that close QApplication
        self._form.select_folder.clicked.connect(self._on_select_folder)
        self._form.restore_defaults.clicked.connect(self._on_restore_defaults)
        self._form.open_screenshots.clicked.connect(self._on_open_folder)
        self._form.view_last_screenshot.clicked.connect(self._on_open_last_screenshot)
        self._form.view_last_location.clicked.connect(self._on_open_last_location)
        self._form.file_name_format_save.clicked.connect(self._on_file_name_format_save)
        self._form.date_format_save.clicked.connect(self._on_date_format_save)

    def _setup_button_labels(self):
        self._form.take_screenshot.setText(f"📷 Screenshot ({self._settings.screenshot_hotkey})")

    def _setup_input_widget_connections(self):
        self._form.select_format.currentTextChanged.connect(
            self._on_format_selection_changed
        )
        self._select_hotkey.keySequenceChanged.connect(self._on_hotkey_changed)
        self._form.minimize_to_tray.stateChanged.connect(
            self._on_minimize_to_tray_changed
        )

    def _tear_down_input_widget_connections(self):
        self._form.select_format.currentTextChanged.disconnect(
            self._on_format_selection_changed
        )
        self._select_hotkey.keySequenceChanged.disconnect(self._on_hotkey_changed)
        self._form.minimize_to_tray.stateChanged.disconnect(
            self._on_minimize_to_tray_changed
        )

    def _load_ui_state_from_settings(self):
        self._form.current_folder.setText(str(self._settings.screenshot_folder))
        self._select_hotkey.setKeySequence(
            QKeySequence(self._settings.screenshot_hotkey)
        )
        self._form.select_format.clear()
        self._form.select_format.addItems(format.name for format in ImageFormat)
        self._form.select_format.setCurrentText(self._settings.image_format.name)
        self._form.file_name_format.setText(self._settings.file_name_format)
        self._form.date_format.setText(self._settings.date_format)
        self._form.minimize_to_tray.setChecked(self._settings.minimize_to_tray)

    @pyqtSlot(bool)
    def _on_file_name_format_save(self, checked: bool):
        if not self._form.file_name_format.hasAcceptableInput():
            return  # should not happen
        self._settings.file_name_format = self._form.file_name_format.text()
        self._form.file_name_format.setPalette(QLineEdit().palette())
        self._form.file_name_format_save.setDisabled(True)

    @pyqtSlot(bool)
    def _on_date_format_save(self, checked: bool):
        if not self._form.date_format.hasAcceptableInput():
            return  # should not happen
        self._settings.date_format = self._form.date_format.text()
        self._form.date_format.setPalette(QLineEdit().palette())
        self._form.date_format_save.setDisabled(True)

    @pyqtSlot(bool)
    def _on_restore_defaults(self, checked: bool):
        self._settings.restore_defaults()
        # Avoid loops by temporarily disenganging connections
        self._tear_down_input_widget_connections()
        self._load_ui_state_from_settings()
        self._setup_input_widget_connections()
        self._setup_button_labels()

    @pyqtSlot(bool)
    def _on_select_folder(self, checked: bool):
        screenshot_folder = QFileDialog.getExistingDirectory(
            self,
            "Choose where to save MSFS screenshots",
            str(self._settings.screenshot_folder),
        )
        if not screenshot_folder:
            return

        self._form.current_folder.setText(screenshot_folder)
        self._settings.screenshot_folder = Path(screenshot_folder)

    @pyqtSlot(str)
    def _on_format_selection_changed(self, new_name: str):
        format = ImageFormat[new_name]
        self._settings.image_format = format

    @pyqtSlot(QKeySequence)
    def _on_hotkey_changed(self, new_hotkey: QKeySequence):
        if not new_hotkey or not new_hotkey.toString():
            return

        self._settings.screenshot_hotkey = new_hotkey.toString()
        self._setup_button_labels()

    @pyqtSlot(int)
    def _on_minimize_to_tray_changed(self, state: int):
        self._settings.minimize_to_tray = state == Qt.CheckState.Checked

    @pyqtSlot(bool)
    def _on_open_folder(self, checked: bool):
        url = QUrl.fromLocalFile(str(self._settings.screenshot_folder))
        QDesktopServices.openUrl(url)

    def _set_last_opened_screenshot(
        self, path: Path, exif_data: Optional[ExifData] = None
    ):
        self._form.view_last_screenshot.setEnabled(True)
        self._last_screenshot = path

        if (
            exif_data
            and exif_data.GPSLatitude is not None
            and exif_data.GPSLongitude is not None
        ):
            self._form.view_last_location.setEnabled(True)
        self._last_exif_data = exif_data

    @pyqtSlot(bool)
    def _on_open_last_screenshot(self, checked: bool):
        if not self._last_screenshot or not self._last_screenshot.is_file():
            self._notification_handler.notify(
                "File no longer exists", color=NotificationColor.error
            )
            return False
        url = QUrl.fromLocalFile(str(self._last_screenshot))
        QDesktopServices.openUrl(url)

    @pyqtSlot(bool)
    def _on_open_last_location(self, checked: bool):
        if not self._last_exif_data:
            return
        latitude = self._last_exif_data.GPSLatitude
        longitude = self._last_exif_data.GPSLongitude

        if latitude is None or longitude is None:
            print("Invalid GPS data for last screenshot")
            return

        url_str = self._maps_url.format(latitude=latitude, longitude=longitude)
        url = QUrl(url_str)
        QDesktopServices.openUrl(url)

    @pyqtSlot(bool)
    def _on_quit_button(self, _):
        self.closed.emit()
        QApplication.quit()

    def closeEvent(self, close_event: QCloseEvent) -> None:
        if self._settings.minimize_to_tray:
            self.showMinimized()
            close_event.ignore()
        else:
            self.closed.emit()
            return super().closeEvent(close_event)

    def changeEvent(self, event: QEvent):
        if event.type() != QEvent.Type.WindowStateChange:
            return super().changeEvent(event)
        if self.isMinimized() and self._settings.minimize_to_tray:
            event.ignore()
            QTimer.singleShot(0, self.hide)
