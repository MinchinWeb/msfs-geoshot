from dataclasses import dataclass
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from enum import Enum

import tzlocal
from PyQt5.QtGui import QGuiApplication, QImageWriter

from ..exif import ExifLocationData, ExifService
from ..sim import SimService, SimServiceError


class ImageFormat(Enum):
    png = "png"
    jpg = "jpg"
    tiff = "tiff"


@dataclass
class _ImageFormatSettings:
    extension: str
    quality: Optional[int]
    compression: Optional[int]
    optimized_write: Optional[bool]
    progressive_scan_write: Optional[bool]


class ScreenShotService:

    _date_format = "%Y-%m-%d-%H%M%S"
    _file_stem_format = "MSFS_{date}"

    _settings_by_image_format: Dict[ImageFormat, _ImageFormatSettings] = {
        # compression is in range 0,100, quality just maps to compression in reverse
        ImageFormat.png: _ImageFormatSettings(
            extension="png",
            quality=None,
            compression=100,
            optimized_write=True,
            progressive_scan_write=True,
        ),
        ImageFormat.jpg: _ImageFormatSettings(
            extension="jpg",
            quality=100,
            compression=None,
            optimized_write=None,
            progressive_scan_write=None,
        ),
        # compression is binary 0/1, quality is ignored
        ImageFormat.tiff: _ImageFormatSettings(
            extension="tiff",
            quality=None,
            compression=1,
            optimized_write=None,
            progressive_scan_write=None,
        ),
    }

    def __init__(
        self, sim_service: SimService, exif_service: ExifService, target_folder: Path
    ):
        self._sim_service = sim_service
        self._exif_service = exif_service
        self._target_folder = target_folder

    def take_screenshot(
        self, image_format: ImageFormat = ImageFormat.tiff
    ) -> Optional[Path]:
        try:
            location_data = self._sim_service.get_current_location()
        except SimServiceError as e:
            print(e)
            return None

        out_path = self._get_new_screenshot_path(image_format)

        self._grab_screenshot(out_path=out_path, image_format=image_format)
        if location_data:
            self._write_metadata(location_data, out_path)

        return out_path

    def _get_new_screenshot_path(self, image_format: ImageFormat) -> Path:
        capture_time = time.time()

        local_timezone = tzlocal.get_localzone()
        capture_datetime = datetime.fromtimestamp(capture_time, tz=local_timezone)
        datetime_string = capture_datetime.strftime(self._date_format)

        image_format_settings = self._settings_by_image_format[image_format]

        file_stem = self._file_stem_format.format(date=datetime_string)
        file_name = f"{file_stem}.{image_format_settings.extension}"

        return self._target_folder / file_name

    def _grab_screenshot(self, out_path: Path, image_format: ImageFormat):
        # TODO: identify actual window rather than using primary screen
        active_screen = QGuiApplication.primaryScreen()
        root_window = active_screen.grabWindow(0)  # type: ignore
        image = root_window.toImage()

        image_format_settings = self._settings_by_image_format[image_format]

        image_writer = QImageWriter()
        image_writer.setFileName(str(out_path))
        image_writer.setFormat(image_format.value.encode())

        if (compression := image_format_settings.compression) is not None:
            image_writer.setCompression(compression)
        if (quality := image_format_settings.quality) is not None:
            image_writer.setQuality(quality)
        if (optimized_write := image_format_settings.optimized_write) is not None:
            image_writer.setOptimizedWrite(optimized_write)
        if (
            progressive_scan_write := image_format_settings.progressive_scan_write
        ) is not None:
            image_writer.setProgressiveScanWrite(progressive_scan_write)

        image_writer.write(image)

    def _write_metadata(self, location_data: ExifLocationData, screenshot: Path):
        self._exif_service.write_data(
            exif_location_data=location_data, image_path=screenshot
        )
