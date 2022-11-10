from pathlib import Path
from typing import Optional, List

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
from qgis.utils import iface


class GpsLogReplayer(QgsNmeaConnection):
    error_occurred = pyqtSignal(str)

    def __init__(self, file: Path, temporal_controller: QgsTemporalNavigationObject):
        self.buffer = QBuffer()
        self.buffer.open(QBuffer.ReadWrite)
        super().__init__(self.buffer)

        self.temporal_controller = temporal_controller
        with open(file, 'rt') as f:
            log = f.readlines()

        # preparse log to scan for time stamps

        # first scan for first date value
        first_date = None
        for sentence in log:
            first_date = GpsLogReplayer.date_from_sentence(sentence)
            if first_date is not None:
                break

        if first_date is None:
            self.error_occurred.emit(self.tr('No date stamp found in log'))
            return

        # then scan for first timestamp
        first_timestamp_utc = None
        for sentence in log:
            first_timestamp_utc = GpsLogReplayer.timestamp_from_sentence(sentence, first_date)
            if first_timestamp_utc is not None:
                break

        if first_timestamp_utc is None:
            self.error_occurred.emit(self.tr('No timestamp found in log'))
            return

        self.sentences = []

        current_date = first_date
        current_utc = first_timestamp_utc
        current_parts = []
        for sentence in log:
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

    @staticmethod
    def date_from_sentence(sentence: str) -> Optional[QDate]:
        if sentence.startswith('$GNRMC'):
            parts = sentence.split(',')

            date = parts[9]
            dd = int(date[:2])
            mm = int(date[2:4])
            yy = int(date[4:6])

            return QDate(yy, mm, dd)

        return None

    @staticmethod
    def timestamp_from_sentence(sentence: str, date: QDate) -> Optional[QDateTime]:
        if sentence.startswith('$GNRMC') or \
                sentence.startswith('$GNGNS') or \
                sentence.startswith('$GNGGA'):

            parts = sentence.split(',')
            timestamp_utc = parts[1]

            hh = int(timestamp_utc[:2])
            mm = int(timestamp_utc[2:4])
            ss = int(timestamp_utc[4:6])
            assert timestamp_utc[6] == '.'
            ms = int(timestamp_utc[7:9]) * 10

            time = QTime(hh, mm, ss, ms)

            if sentence.startswith('$GNRMC'):
                # update date
                date = parts[9]
                dd = int(date[:2])
                mm = int(date[2:4])
                yy = int(date[4:6]) + 2000
                date = QDate(yy, mm, dd)

            timestamp = QDateTime(date, time, Qt.TimeSpec.UTC)
            return timestamp

        return None

    def temporal_extents_changed(self, range):
        # find closest sentences

        prev_sentence = None
        next_sentence = None
        for sentence in self.sentences:
            if range.contains(sentence[0]):
                self.send_sentence(sentence[1])
                return

            if sentence[0] < range.begin():
                prev_sentence = sentence
            if sentence[0] > range.begin() and not next_sentence:
                next_sentence = sentence
                break

        if not prev_sentence or not next_sentence:
            return

        if prev_sentence[0].secsTo(range.begin()) < range.begin().secsTo(next_sentence[0]):
            self.send_sentence(prev_sentence[1])
        else:
            self.send_sentence(next_sentence[1])

    def send_sentence(self, sentence: List[str]):
        nmea_msg = ('\r\n'.join(sentence)).encode()

        pos = self.buffer.pos()
        self.buffer.write(nmea_msg)
        self.buffer.seek(pos)

