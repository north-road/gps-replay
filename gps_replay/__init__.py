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

"""
GPS Replay Plugin
"""

from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import (
    QCoreApplication
)
from qgis.PyQt.QtWidgets import (
    QAction,
    QFileDialog
)

from .gps_replayer import GpsLogReplayer
from .gui import GuiUtils


def classFactory(iface):
    """
    Creates the plugin instance
    """
    return GpsReplayPlugin(iface)


class GpsReplayPlugin:
    """
    GPS Replay Plugin
    """

    def __init__(self, iface):
        self.iface = iface
        self.replay_action: Optional[QAction] = None

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

    # pylint: disable=missing-function-docstring

    def initProcessing(self):
        """Create the Processing provider"""

        # maybe in future?

    def initGui(self):
        self.initProcessing()

        self.replay_action = QAction(self.tr('Replay GPS Log'), self.iface.mainWindow())
        self.replay_action.setIcon(GuiUtils.get_icon('icon.svg'))
        self.replay_action.triggered.connect(self.select_file)
        self.iface.pluginToolBar().addAction(self.replay_action)

    def unload(self):
        if self.replay_action is not None:
            self.replay_action.deleteLater()
            self.replay_action = None

    # pylint: enable=missing-function-docstring

    def select_file(self):
        """
        Asks user for a log file to replay
        """
        file, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(),
                                              self.tr('GPS Replay'),
                                              self.tr('Select log to replay'))
        if file:
            self.create_replayer(Path(file))

    def create_replayer(self, file_path: Path):
        """
        Creates a GPS log replayer and attaches it to the QGIS instance
        """
        replayer = GpsLogReplayer(file_path, self.iface.mapCanvas().temporalController())
        replayer.error_occurred.connect(self._log_error)
        self.iface.setGpsPanelConnection(replayer)

    def _log_error(self, error: str):
        """
        Shows an error to the user via message bar
        """
        self.iface.messageBar().pushWarning('GPS Replayer', error)
