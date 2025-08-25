import os
import sqlite3

from PyQt5.QtCore import QObject, pyqtSlot

import Segment


class DatabaseHandler(QObject):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self.connect()
        self.create_tables()

    def __del__(self):
        self.commit()
        self.con.close()

    def connect(self):
        self.con = sqlite3.connect(self.db_path)
        self.cursor = self.con.cursor()

    def commit(self):
        self.con.commit()

    def create_tables(self):
        """Creates the necessary tables for the database"""

        # table recording: filename, directory
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS recording(
            filename CHAR PRIMARY KEY,
            directory CHAR)"""
        )

        # table operator: name
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS operator(
            operator_id INTEGER PRIMARY KEY,
            name CHAR)"""
        )

        # table operator: name
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS filters(
            filter_id INTEGER PRIMARY KEY,
            name CHAR)"""
        )
        # table species: scientific_name, common_name
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS species(
            scientific_name CHAR PRIMARY KEY,
            common_name CHAR)"""
        )

        # table calltypes: scientific_name, calltype
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS calltypes(
            calltype_id INTEGER PRIMARY KEY,
            scientific_name CHAR,
            calltype CHAR,
            FOREIGN KEY(scientific_name) REFERENCES species(scientific_name))"""
        )

        # table segments: filename, start, end, low, high, operator_id
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS segments(
            segment_id INTEGER PRIMARY KEY,
            filename CHAR,
            start REAL,
            end REAL,
            low REAL,
            high REAL,
            operator_id INTEGER,
            FOREIGN KEY(filename) REFERENCES recording(filename),
            FOREIGN KEY(operator_id) REFERENCES operator(operator_id))"""
        )

        # table segment_species: connects segments and species
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS segment_species(
            species_scientific_name CHAR,
            confidence REAL,
            segment_id INTEGER,
            filter_id INTEGER,
            calltype_id INTEGER,
            FOREIGN KEY(species_scientific_name) REFERENCES species(scientific_name),
            FOREIGN KEY(segment_id) REFERENCES segments(segment_id),
            FOREIGN KEY(filter_id) REFERENCES filters(filter_id),
            FOREIGN KEY(calltype_id) REFERENCES calltypes(calltype_id))
            """
        )

        self.cursor.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_segments_unique ON segments (filename, start, end, low, high)"""
        )
        self.cursor.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_segment_species_unique on segment_species(species_scientific_name, confidence, segment_id, filter_id, calltype_id)"""
        )
        self.cursor.execute(
            """CREATE INDEX IF NOT EXISTS idx_segment_species_segment_id on segment_species(segment_id)"""
        )
        self.cursor.execute(
            """CREATE INDEX IF NOT EXISTS idx_recording_directory on recording(directory)"""
        )

    @pyqtSlot(Segment.SegmentList, str)
    def insert_segments(self, segmentList, filename):
        dirname = os.path.dirname(filename)
        filename = os.path.basename(filename)
        op_id = self.add_operator(segmentList.metadata["Operator"])
        self.add_file(filename, dirname)

        # add or update segments
        for segment in segmentList:
            seg_dict = {
                "start": segment[0],
                "end": segment[1],
                "low": segment[2],
                "high": segment[3],
                "operator_id": op_id,
                "filename": filename,
            }
            self.insert_segment(seg_dict)
            seg_id = self.cursor.fetchone()[0]
            for species in segment[4]:
                self.add_species(species, seg_id)
        self.commit()

    def add_operator(self, operator):
        self.cursor.execute(
            """SELECT operator_id FROM operator WHERE name = (?)""", (operator,)
        )
        existing_row_id = self.cursor.fetchone()
        if existing_row_id:
            op_id = existing_row_id[0]
        else:
            self.cursor.execute(
                """INSERT INTO operator(name) VALUES (?)""", (operator,)
            )
            op_id = self.cursor.lastrowid
        return op_id

    def add_filter(self, filter):
        self.cursor.execute(
            """SELECT filter_id FROM filters WHERE name = (?)""", (filter,)
        )
        existing_row_id = self.cursor.fetchone()
        if existing_row_id:
            filter_id = existing_row_id[0]
        else:
            self.cursor.execute(
                """INSERT INTO filters(name) VALUES (?) RETURNING filter_id""",
                (filter,),
            )
            filter_id = self.cursor.fetchone()[0]
        return filter_id

    def add_calltype(self, data):
        self.cursor.execute(
            """SELECT calltype_id FROM calltypes WHERE calltype = (:calltype) AND scientific_name = (:scientific_name)""",
            data,
        )

        existing_row_id = self.cursor.fetchone()
        if existing_row_id:
            calltype_id = existing_row_id[0]
        else:
            self.cursor.execute(
                """INSERT INTO calltypes(scientific_name, calltype) VALUES (:scientific_name, :calltype) RETURNING calltype_id""",
                data,
            )
            calltype_id = self.cursor.fetchone()[0]
        return calltype_id

    def add_file(self, filename, dirname):
        file_dict = {"filename": filename, "directory": dirname}
        self.cursor.execute(
            """INSERT OR REPLACE INTO recording
                VALUES (:filename, :directory)""",
            file_dict,
        )

    def insert_segment(self, segment):
        self.cursor.execute(
            """INSERT INTO segments(filename, start, end, low, high, operator_id)
                VALUES (:filename, :start, :end, :low, :high, :operator_id)
                ON CONFLICT (filename, start, end, low, high) DO UPDATE SET operator_id = :operator_id
                RETURNING segment_id""",
            segment,
        )

    def delete_dir_segments(self, dir):
        self.cursor.execute(
            """DELETE FROM segments 
            WHERE filename IN (
                SELECT segments.filename FROM segments
                INNER JOIN recording ON segments.filename=recording.filename
                WHERE recording.directory LIKE ?
            ) RETURNING segment_id""",
            (dir + "%",),
        )
        self.delete_orphan_segment_species()
        self.delete_orphan_recordings()

    def delete_file_segments(self, file):
        self.cursor.execute(
            """DELETE FROM segments 
            WHERE filename IN (
                SELECT segments.filename FROM segments
                INNER JOIN recording ON segments.filename=recording.filename
                WHERE segments.filename = ? AND recording.directory = ?
            ) RETURNING segment_id""",
            (os.path.basename(file), os.path.dirname(file)),
        )
        self.delete_orphan_segment_species()

    def delete_segment(self, filename, dirname, segment):
        seg = {
            "start": segment[0],
            "end": segment[1],
            "low": segment[2],
            "high": segment[3],
            "filename": os.path.basename(filename),
            "directory": dirname,
        }

        self.cursor.execute(
            """DELETE FROM segments
                WHERE segment_id IN (SELECT segments.segment_id FROM segments 
                INNER JOIN recording ON segments.filename=recording.filename
                WHERE start = (:start) AND 
                end = (:end) AND 
                low = (:low) AND 
                high = (:high) AND
                recording.filename = (:filename) AND 
                recording.directory = (:directory)
                )""",
            seg,
        )
        self.delete_orphan_segment_species()

    def get_segment_id(self, segment):
        self.cursor.execute(
            """SELECT segments.segment_id FROM segments 
                INNER JOIN recording ON segments.filename=recording.filename
                WHERE start = (:start) AND 
                end = (:end) AND 
                segments.filename = (:filename) AND 
                low = (:low) AND 
                high = (:high) AND
                recording.directory = (:directory)""",
            segment,
        )
        return self.cursor.fetchone()[0]

    def add_species(self, species_list, seg_id):
        if "filter" not in species_list.keys():
            species_list["filter"] = "M"
        filter_id = self.add_filter(species_list["filter"])

        sp_dict = {
            "scientific_name": species_list["species"],
            "common_name": species_list["species"],
            "confidence": species_list["certainty"],
            "segment_id": seg_id,
            "filter_id": filter_id,
            "calltype": species_list["calltype"]
            if "calltype" in species_list.keys()
            else "non-specified",
        }
        self.cursor.execute(
            """INSERT INTO species
                SELECT :scientific_name, :common_name
                WHERE NOT EXISTS(SELECT 1 FROM species 
                WHERE scientific_name = (:scientific_name) 
                AND common_name = (:common_name))""",
            sp_dict,
        )

        sp_dict["calltype_id"] = self.add_calltype(sp_dict)

        self.cursor.execute(
            """INSERT INTO segment_species
                SELECT :scientific_name, :confidence, :segment_id, :filter_id, :calltype_id
                WHERE NOT EXISTS(SELECT 1 FROM segment_species 
                WHERE species_scientific_name = (:scientific_name) 
                AND confidence = (:confidence) 
                AND segment_id = (:segment_id)
                AND filter_id = (:filter_id)
                AND calltype_id = (:calltype_id))""",
            sp_dict,
        )

    def update_segment(self, old, new, directory, filename):
        segment = {
            "start": old[0],
            "end": old[1],
            "low": old[2],
            "high": old[3],
            "start_new": new[0],
            "end_new": new[1],
            "low_new": new[2],
            "high_new": new[3],
            "filename": filename,
            "directory": directory,
        }
        self.cursor.execute(
            """UPDATE segments
               SET start = (:start_new), end = (:end_new), low = (:low_new), high = (:high_new)
               WHERE (start, end, filename, CAST(low as INTEGER), CAST(high as INTEGER)) IN (
               SELECT start, end, segments.filename, CAST(low as INTEGER), CAST(high as INTEGER)
               FROM segments 
               INNER JOIN recording ON segments.filename=recording.filename
               WHERE segments.start = (:start) AND
               segments.end = (:end) AND
               segments.filename = (:filename) AND
               recording.directory = (:directory))
               """,
            segment,
        )

    def update_segment_species(self, new, directory, filename, operator):
        op_id = self.add_operator(operator)
        segment = {
            "start": new[0],
            "end": new[1],
            "low": new[2],
            "high": new[3],
            "filename": filename,
            "directory": directory,
            "operator_id": op_id,
        }
        self.insert_segment(segment)
        seg_id = self.cursor.fetchone()[0]
        self.delete_segment_species(seg_id)
        for sp in new[4]:
            self.add_species(sp, seg_id)

    def delete_segment_species(self, segment_id):
        self.cursor.execute(
            """
            DELETE FROM segment_species WHERE segment_id = (?)
        """,
            (segment_id,),
        )

    def get_files_with_species(self, species, dirname, minconf):
        self.cursor.execute(
            """SELECT recording.filename, recording.directory FROM recording 
            INNER JOIN segments ON recording.filename=segments.filename 
            INNER JOIN segment_species ON segments.segment_id = segment_species.segment_id 
            WHERE recording.directory LIKE ? AND segment_species.species_scientific_name = (?) AND
            segment_species.confidence >= ? GROUP BY recording.filename""",
            (dirname + "%", species, minconf),
        )
        return self.cursor.fetchall()

    def get_dir_species_confidence(self, dirname):
        self.cursor.execute(
            """SELECT segment_species.species_scientific_name, segment_species.confidence FROM recording 
            CROSS JOIN segments ON recording.filename=segments.filename 
            CROSS JOIN segment_species ON segments.segment_id = segment_species.segment_id 
            WHERE recording.directory = ?""",
            (dirname,),
        )
        return self.cursor.fetchall()

    def get_grouped_dir_species_segments(self, dirname, species, minconf):
        self.cursor.execute(
            """SELECT recording.directory, recording.filename, segments.start, segments.end, 
            segment_species.species_scientific_name, MAX(segment_species.confidence) FROM recording 
            INNER JOIN segments ON recording.filename=segments.filename 
            INNER JOIN segment_species ON segments.segment_id = segment_species.segment_id 
            WHERE recording.directory LIKE ? AND segment_species.species_scientific_name = (?) AND
            segment_species.confidence >= ? GROUP BY segments.start, segments.end, segment_species.species_scientific_name""",
            (dirname + "%", species, minconf),
        )
        return self.cursor.fetchall()

    def get_dir_species_segments(self, dirname, species, minconf):
        self.cursor.execute(
            """SELECT recording.directory, recording.filename, segments.start, segments.end,
            segments.low, segments.high, 
            segment_species.species_scientific_name, segment_species.confidence, 
            calltypes.calltype, filters.name FROM recording 
            INNER JOIN segments ON recording.filename = segments.filename 
            INNER JOIN segment_species ON segments.segment_id = segment_species.segment_id 
            INNER JOIN calltypes ON segment_species.calltype_id = calltypes.calltype_id
            INNER JOIN filters ON segment_species.filter_id = filters.filter_id
            WHERE recording.directory LIKE ? AND segment_species.species_scientific_name = (?) AND
            segment_species.confidence >= ?""",
            (dirname + "%", species, minconf),
        )
        return self.cursor.fetchall()

    def get_grouped_dir_segments(self, dirname, minconf):
        self.cursor.execute(
            """SELECT recording.directory, recording.filename, segments.start, segments.end, 
            segment_species.species_scientific_name, MAX(segment_species.confidence) FROM recording 
            INNER JOIN segments ON recording.filename=segments.filename 
            INNER JOIN segment_species ON segments.segment_id = segment_species.segment_id 
            WHERE recording.directory LIKE ? AND
            segment_species.confidence >= ? GROUP BY segments.start, segments.end, segment_species.species_scientific_name""",
            (dirname + "%", minconf),
        )
        return self.cursor.fetchall()

    def get_dir_segments(self, dirname, minconf=0):
        self.cursor.execute(
            """SELECT recording.directory, recording.filename, segments.start, segments.end, 
            segments.low, segments.high, 
            segment_species.species_scientific_name, segment_species.confidence, 
            calltypes.calltype, filters.name FROM recording 
            INNER JOIN segments ON recording.filename=segments.filename 
            INNER JOIN segment_species ON segments.segment_id = segment_species.segment_id
            INNER JOIN calltypes ON segment_species.calltype_id = calltypes.calltype_id
            INNER JOIN filters ON segment_species.filter_id = filters.filter_id
            WHERE recording.directory LIKE ? AND
            segment_species.confidence >= ?""",
            (dirname + "%", minconf),
        )
        return self.cursor.fetchall()

    def get_files_species_confidence(self, dirname):
        self.cursor.execute(
            """SELECT recording.directory, recording.filename, segment_species.species_scientific_name, segment_species.confidence FROM recording 
            CROSS JOIN segments ON recording.filename=segments.filename 
            CROSS JOIN segment_species ON segments.segment_id = segment_species.segment_id 
            WHERE recording.directory = ? """,
            (dirname,),
        )
        return self.cursor.fetchall()

    def get_file_segments(self, filename, dirname):
        self.cursor.execute(
            """SELECT segments.start, segments.end, segments.low, segments.high,
            segment_species.species_scientific_name, segment_species.confidence,
            filters.name, calltypes.calltype FROM recording 
            INNER JOIN segments ON recording.filename=segments.filename 
            INNER JOIN segment_species ON segments.segment_id = segment_species.segment_id
            INNER JOIN filters ON segment_species.filter_id = filters.filter_id
            INNER JOIN calltypes ON segment_species.calltype_id = calltypes.calltype_id  
            WHERE recording.filename = ? AND recording.directory = ?""",
            (filename, dirname),
        )
        return self.cursor.fetchall()

    def delete_orphan_segment_species(self):
        self.cursor.execute("""DELETE FROM segment_species 
            WHERE segment_id NOT IN 
            (SELECT segment_id FROM segments)""")

    def delete_orphan_recordings(self):
        self.cursor.execute("""DELETE FROM recording 
            WHERE filename NOT IN 
            (SELECT filename FROM segments)""")
