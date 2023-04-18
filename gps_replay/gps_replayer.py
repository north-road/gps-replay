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
GPS Replayer
"""

from enum import Enum
from pathlib import Path
from typing import Optional, List

import re
from qgis.PyQt.QtCore import (
    QBuffer,
    Qt,
    QDate,
    QTime,
    QDateTime,
    pyqtSignal
)
from qgis.core import (
    QgsNmeaConnection,
    QgsDateTimeRange,
    QgsTemporalNavigationObject
)

RMC_SENTENCE_RX = re.compile(r'^\$G.RMC.*$')
GNS_SENTENCE_RX = re.compile(r'^\$G.GNS.*$')
GGA_SENTENCE_RX = re.compile(r'^\$G.GGA.*$')
ZDA_SENTENCE_RX = re.compile(r'^\$G.ZDA.*$')


class NmeaSentenceType(Enum):
    """
    NMEA Sentence types (a small subset!)
    """
    RMC = 1
    GNS = 2
    GGA = 3
    ZDA = 4

    @staticmethod
    def from_sentence(sentence: str) -> Optional['NmeaSentenceType']:
        """
        Deduces the NMEA sentence type from a sentence
        """
        if RMC_SENTENCE_RX.match(sentence):
            return NmeaSentenceType.RMC
        if GNS_SENTENCE_RX.match(sentence):
            return NmeaSentenceType.GNS
        if GGA_SENTENCE_RX.match(sentence):
            return NmeaSentenceType.GGA
        if ZDA_SENTENCE_RX.match(sentence):
            return NmeaSentenceType.ZDA
        return None


class GpsLogReplayer(QgsNmeaConnection):
    """
    GPS replayer, a QGIS GPS connection which replays a previously recorded log
    """

    error_occurred = pyqtSignal(str)

    def __init__(self, file: Path, temporal_controller: QgsTemporalNavigationObject):
        self.buffer = QBuffer()
        self.buffer.open(QBuffer.ReadWrite)
        super().__init__(self.buffer)

        self.temporal_controller = temporal_controller
        with open(file, 'rt', encoding='utf-8') as f:
            self.log = f.readlines()

        self.sentences = []
        self._valid = False

    def is_valid(self) -> bool:
        """
        Returns True if the recorder is in a valid state
        """
        return self._valid

    def load(self):
        """
        Loads the log file
        """
        # preparse log to scan for time stamps

        # first scan for first date value
        first_date = None
        for sentence in self.log:
            first_date = GpsLogReplayer.date_from_sentence(sentence)
            if first_date is not None:
                break

        if first_date is None:
            self.error_occurred.emit(self.tr('No date stamp found in log'))
            return

        # then scan for first timestamp
        first_timestamp_utc = None
        for sentence in self.log:
            first_timestamp_utc = GpsLogReplayer.timestamp_from_sentence(sentence, first_date)
            if first_timestamp_utc is not None:
                break

        if first_timestamp_utc is None:
            self.error_occurred.emit(self.tr('No timestamp found in log'))
            return

        current_date = first_date
        current_utc = first_timestamp_utc
        current_parts = []
        for sentence in self.log:
            sentence = sentence.strip()
            if not sentence:
                continue

            new_timestamp = GpsLogReplayer.timestamp_from_sentence(sentence, current_date)
            if new_timestamp is not None and new_timestamp != current_utc:

                if current_parts:
                    self.sentences.append((current_utc, current_parts))

                current_utc = new_timestamp
                current_date = new_timestamp.date()
                current_parts = [sentence]

            else:
                current_parts.append(sentence)

        if current_parts:
            self.sentences.append((current_utc, current_parts))

        time_range = QgsDateTimeRange(self.sentences[0][0], self.sentences[-1][0])

        self.temporal_controller.setTemporalExtents(time_range)
        self.temporal_controller.updateTemporalRange.connect(self.temporal_extents_changed)
        self._valid = True

    @staticmethod
    def date_from_sentence(sentence: str) -> Optional[QDate]:
        """
        Tries to extract a date value from a NMEA sentence
        """
        if NmeaSentenceType.from_sentence(sentence) == NmeaSentenceType.RMC:
            parts = sentence.split(',')

            date = parts[9]
            dd = int(date[:2])
            mm = int(date[2:4])
            yy = int(date[4:6])
            if yy < 80:
                yy += 2000
            else:
                yy += 1900

            return QDate(yy, mm, dd)

        if NmeaSentenceType.from_sentence(sentence) == NmeaSentenceType.ZDA:
            parts = sentence.split(',')
            dd = int(parts[2])
            mm = int(parts[3])
            yy = int(parts[4])
            return QDate(yy, mm, dd)

        return None

    @staticmethod
    def timestamp_from_sentence(sentence: str, date: QDate) -> Optional[QDateTime]:
        """
        Tries to extract a timestamp value from a NMEA sentence
        """
        sentence_type = NmeaSentenceType.from_sentence(sentence)
        if sentence_type in (
                NmeaSentenceType.RMC,
                NmeaSentenceType.GNS,
                NmeaSentenceType.GGA,
                NmeaSentenceType.ZDA):

            parts = sentence.split(',')
            timestamp_utc = parts[1]
            if timestamp_utc:
                hh = int(timestamp_utc[:2])
                mm = int(timestamp_utc[2:4])
                ss = int(timestamp_utc[4:6])
                ms = 0
                if len(timestamp_utc) > 6:    # there is decimal part
                    ms = int(float(timestamp_utc[6:]) * 1000)

                time = QTime(hh, mm, ss, ms)

                if sentence_type == NmeaSentenceType.RMC:
                    # update date
                    date = parts[9]
                    dd = int(date[:2])
                    mm = int(date[2:4])
                    yy = int(date[4:6])
                    if yy < 80:
                        yy += 2000
                    else:
                        yy += 1900
                    date = QDate(yy, mm, dd)

                timestamp = QDateTime(date, time, Qt.TimeSpec.UTC)
                return timestamp

        return None

    def temporal_extents_changed(self, temporal_range):
        """
        Called when the temporal controller visible range is changed
        """

        # find closest sentences
        prev_sentence = None
        next_sentence = None
        for sentence in self.sentences:
            if temporal_range.contains(sentence[0]):
                self.send_sentence(sentence[1])
                return

            if sentence[0] < temporal_range.begin():
                prev_sentence = sentence
            if sentence[0] > temporal_range.begin() and not next_sentence:
                next_sentence = sentence
                break

        if not prev_sentence or not next_sentence:
            return

        if prev_sentence[0].secsTo(temporal_range.begin()) < temporal_range.begin().secsTo(
                next_sentence[0]):
            self.send_sentence(prev_sentence[1])
        else:
            self.send_sentence(next_sentence[1])

    def send_sentence(self, sentence: List[str]):
        """
        Sends a sentence as a GPS messages
        """
        nmea_msg = ('\r\n'.join(sentence) + '\r\n').encode()

        pos = self.buffer.pos()
        self.buffer.write(nmea_msg)
        self.buffer.seek(pos)
