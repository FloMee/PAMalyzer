import sqlite3
import os


class DatabaseHandler:
    def __init__(self, db_path):
        self.db_path = db_path
        self.connect()
        self.create_tables()

    def connect(self):
        self.con = sqlite3.connect(self.db_path)
        self.cursor = self.con.cursor()

    def create_tables(self):
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS recording(filename CHAR PRIMARY KEY,
            directory CHAR)"""
        )
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS operator(name CHAR)""")
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS species(scientific_name CHAR,
            common_name CHAR)"""
        )
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS segment_species(species_scientific_name,
            confidence REAL,
            segment_id,
            FOREIGN KEY(species_scientific_name) REFERENCES species(scientific_name),
            FOREIGN KEY(segment_id) REFERENCES segments(rowid))"""
        )
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS segments(filename CHAR,
            start REAL,
            end REAL,
            low REAL,
            high REAL,
            operator_id,
            FOREIGN KEY(filename) REFERENCES recording(filename),
            FOREIGN KEY(operator_id) REFERENCES operator(rowid))
            """
        )
        self.cursor.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_segments_unique ON segments (filename, start, end, low, high)"""
        )

    def insert_segments(self, segmentList, operator, filename):
        dirname = os.path.dirname(filename)
        filename = os.path.basename(filename)
        op_id = self.add_operator(segmentList.metadata["Operator"])
        self.add_file(filename, dirname)

        # get current list of segments stored in the database
        seglist_db = self.get_file_segments(filename)
        # create list of segments from current segmentList
        seglist = [(seg[0], seg[1], seg[2], seg[3], sp['species'], sp['certainty']) for seg in segmentList for sp in seg[4]]

        # delete from db if not in segmentList
        for seg_sp in seglist_db:
            if seg_sp not in seglist:
                self.delete_segment_species(seg_sp)

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
            seg_id = self.get_segment_id(seg_dict)
            for species in segment[4]:
                self.add_species(species, seg_id)
        self.con.commit()

    def add_operator(self, operator):
        self.cursor.execute(
            """SELECT rowid FROM operator WHERE name = (?)""", (operator,)
        )
        existing_row_id = self.cursor.fetchone()
        if existing_row_id:
            op_id = existing_row_id[0]
        else:
            self.cursor.execute("""INSERT INTO operator VALUES (?)""", (operator,))
            self.con.commit()
            op_id = self.cursor.lastrowid
        return op_id

    def add_file(self, filename, dirname):
        file_dict = {"filename": filename, "directory": dirname}
        self.cursor.execute(
            """INSERT OR REPLACE INTO recording
                VALUES (:filename, :directory)""",
            file_dict,
        )
        self.con.commit()

    def insert_segment(self, segment):

        self.cursor.execute(
            """INSERT INTO segments
                VALUES (:filename, :start, :end, :low, :high, :operator_id)
                ON CONFLICT (filename, start, end, low, high) DO UPDATE SET operator_id = :operator_id""",
            segment,
        )
        self.con.commit()

    def get_segment_id(self, segment):
        self.cursor.execute(
            """SELECT rowid FROM segments 
                WHERE start = (:start) AND 
                end = (:end) AND 
                filename = (:filename) AND 
                low = (:low) AND 
                high = (:high) AND
                operator_id = (:operator_id)""",
            segment,
        )
        return self.cursor.fetchone()[0]

    def add_species(self, species_list, seg_id):
        sp_dict = {
            "scientific_name": species_list["species"],
            "common_name": species_list["species"],
            "confidence": species_list["certainty"],
            "segment_id": seg_id,
        }
        self.cursor.execute(
            """INSERT INTO species
                SELECT :scientific_name, :common_name
                WHERE NOT EXISTS(SELECT 1 FROM species 
                WHERE scientific_name = (:scientific_name) 
                AND common_name = (:common_name))""",
            sp_dict,
        )
        self.cursor.execute(
            """INSERT INTO segment_species
                SELECT :scientific_name, :confidence, :segment_id
                WHERE NOT EXISTS(SELECT 1 FROM segment_species 
                WHERE species_scientific_name = (:scientific_name) 
                AND confidence = (:confidence) 
                AND segment_id = (:segment_id))""",
            sp_dict,
        )

    def get_files_with_species(self, species, dirname, minconf):
        self.cursor.execute(
            """SELECT recording.filename, recording.directory FROM recording 
            INNER JOIN segments ON recording.filename=segments.filename 
            INNER JOIN segment_species ON segments.rowid = segment_species.segment_id 
            WHERE recording.directory LIKE ? AND segment_species.species_scientific_name = (?) AND
            segment_species.confidence >= ? GROUP BY recording.filename""",
            (os.path.abspath(dirname) + "%", species, minconf),
        )
        return self.cursor.fetchall()

    def get_dir_species_max_confidence(self, dirname):
        self.cursor.execute(
            """SELECT segment_species.species_scientific_name, MAX(segment_species.confidence) FROM recording 
            INNER JOIN segments ON recording.filename=segments.filename 
            INNER JOIN segment_species ON segments.rowid = segment_species.segment_id 
            WHERE recording.directory LIKE ? GROUP BY segment_species.species_scientific_name""",
            (dirname.absoluteFilePath() + "%",),
        )
        return self.cursor.fetchall()

    def get_file_species_max_confidence(self, dirname):
        self.cursor.execute(
            """SELECT recording.directory, recording.filename, segment_species.species_scientific_name, MAX(segment_species.confidence) FROM recording 
            INNER JOIN segments ON recording.filename=segments.filename 
            INNER JOIN segment_species ON segments.rowid = segment_species.segment_id 
            WHERE recording.directory LIKE ? GROUP BY recording.filename, segment_species.species_scientific_name""",
            (dirname + "%",),
        )
        return self.cursor.fetchall()

    def get_file_segments(self, filename):
        self.cursor.execute(
            """SELECT segments.start, segments.end, segments.low, segments.high, segment_species.species_scientific_name, segment_species.confidence FROM recording 
            INNER JOIN segments ON recording.filename=segments.filename 
            INNER JOIN segment_species ON segments.rowid = segment_species.segment_id 
            WHERE recording.filename = ? """,
            (filename,),
        )
        return self.cursor.fetchall()

    def delete_segment_species(self, seg_species):
        seg_dict = {"start": seg_species[0],
                "end": seg_species[1],
                "low": seg_species[2],
                "high": seg_species[3],
                "species": seg_species[4],
                "certainty": seg_species[5]}

        self.cursor.execute(
            """DELETE FROM segment_species WHERE
            species_scientific_name = :species AND confidence = :certainty""",
            seg_dict,
        )

        self.cursor.execute(
            """DELETE FROM segments WHERE NOT EXISTS (
            SELECT 1 FROM segment_species WHERE segment_species.segment_id = segments.rowid)
            AND
            start = (:start) AND end = (:end) AND low = (:low) AND high = (:high)""",
            seg_dict,
        )
        self.con.commit()
