# -----------------------------------------------------------
# Copyright (C) 2022 Nyall Dawson
# -----------------------------------------------------------
# Licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# ---------------------------------------------------------------------

from pathlib import Path
from qgis.PyQt.QtCore import (
    QCoreApplication
)

from .gps_replayer import GpsLogReplayer
from .gui import GuiUtils


def classFactory(iface):
    return GpsReplayPlugin(iface)


class GpsReplayPlugin:
    def __init__(self, iface):
        self.iface = iface

    @staticmethod
    def tr(message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('GpsReplay', message)

    def initProcessing(self):
        """Create the Processing provider"""

        # maybe in future?
        pass

    def initGui(self):
        self.initProcessing()

    def unload(self):
        pass

    def create_replayer(self, file_path: Path):
        replayer = GpsLogReplayer(file_path, self.iface.mapCanvas().temporalController())
        replayer.error_occurred.connect(self.log_error)
        self.iface.setGpsPanelConnection(replayer)

    def log_error(self, error: str):
        self.iface.messageBar().pushWarning('GPS Replayer', error)
